"""Conservative TourAPI enrichment for explicitly curated ``WaterSpot`` rows.

This module intentionally has no discovery or object-creation path.  It only
calls ``detailCommon2`` through the typed provider client for an existing spot's
explicit ``tourapi_id`` and updates that same database row.
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from typing import Iterable, Protocol
from urllib.parse import parse_qsl, urlsplit

from django.db import transaction
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.providers.base import ProviderResult
from services.providers.tour_api import TourApiClient, TourPlaceDetail


FIELD_ORDER = ("name", "address", "lat", "lng", "image_url", "description")
PROVENANCE_FIELD_ORDER = (
    "catalog_source",
    "catalog_source_url",
    "catalog_verified_at",
    "catalog_verification",
)
ALLOWED_LANGUAGES = frozenset(TourApiClient.SERVICE_BY_LANGUAGE)
_BLOCKED_HTML_ELEMENTS = frozenset(
    {"script", "style", "template", "noscript", "iframe", "object", "svg", "math"}
)
_BREAK_HTML_ELEMENTS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
)


class CatalogEnrichmentError(RuntimeError):
    """A sanitized catalog-contract failure safe to show from a command."""


class TourDetailClient(Protocol):
    @property
    def language(self) -> str: ...

    def fetch_detail(self, content_id: str) -> ProviderResult[TourPlaceDetail]: ...


@dataclass(frozen=True, slots=True)
class TourSourceProvenance:
    provider: str
    public_source_url: str
    endpoint: str
    content_id: str
    language: str
    provider_modified_at: datetime | None


@dataclass(frozen=True, slots=True)
class SpotEnrichmentResult:
    spot_id: int
    status: str
    changed_fields: tuple[str, ...]
    provenance: TourSourceProvenance | None


@dataclass(frozen=True, slots=True)
class TourEnrichmentReport:
    results: tuple[SpotEnrichmentResult, ...]
    dry_run: bool
    overwrite: bool

    @property
    def fetched_details(self) -> int:
        return sum(result.provenance is not None for result in self.results)

    @property
    def changed_spots(self) -> int:
        return sum(bool(result.changed_fields) for result in self.results)

    @property
    def skipped_spots(self) -> int:
        return sum(result.status.startswith("skipped_") for result in self.results)


@dataclass(frozen=True, slots=True)
class _PreparedEnrichment:
    spot_id: int
    expected_content_id: str
    detail: TourPlaceDetail
    provenance: TourSourceProvenance


class _PlainTextExtractor(HTMLParser):
    """Extract visible text while discarding executable/embedded element bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.casefold()
        if tag in _BLOCKED_HTML_ELEMENTS:
            self.blocked_depth += 1
            self.parts.append(" ")
        elif self.blocked_depth == 0 and tag in _BREAK_HTML_ELEMENTS:
            self.parts.append(" ")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if self.blocked_depth == 0 and tag.casefold() in _BREAK_HTML_ELEMENTS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in _BLOCKED_HTML_ELEMENTS and self.blocked_depth:
            self.blocked_depth -= 1
            self.parts.append(" ")
        elif self.blocked_depth == 0 and tag in _BREAK_HTML_ELEMENTS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.blocked_depth == 0:
            self.parts.append(data)


def sanitize_provider_html(value: str | None) -> str:
    """Return normalized visible plain text, including for entity-encoded markup.

    Parsing is repeated a bounded number of times so text such as
    ``&lt;script&gt;...`` cannot turn back into active-looking markup after entity
    decoding. Malformed blocked elements fail closed by suppressing their tail.
    """

    if not isinstance(value, str) or not value.strip():
        return ""
    candidate = value
    for _ in range(5):
        parser = _PlainTextExtractor()
        try:
            parser.feed(candidate)
            parser.close()
        except (AssertionError, ValueError):
            return ""
        extracted = html.unescape("".join(parser.parts))
        if extracted == candidate:
            candidate = extracted
            break
        candidate = extracted
    # Make the last decoded layer pass through the element filter as well. If
    # deeply nested entities remain, they stay encoded text rather than markup.
    final_parser = _PlainTextExtractor()
    try:
        final_parser.feed(candidate)
        final_parser.close()
    except (AssertionError, ValueError):
        return ""
    candidate = "".join(final_parser.parts).replace("<", " ").replace(">", " ")
    candidate = "".join(
        character
        if character in {"\n", "\r", "\t"} or ord(character) >= 32
        else " "
        for character in candidate
    )
    return re.sub(r"\s+", " ", candidate.replace("\xa0", " ")).strip()


def _safe_https_image_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or any(ord(character) < 32 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        # Accessing port also rejects malformed bracket/port forms.
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "\\" in parsed.netloc
    ):
        return None
    sensitive_query_terms = (
        "auth",
        "credential",
        "key",
        "password",
        "secret",
        "signature",
        "token",
    )
    try:
        query_names = tuple(name.casefold() for name, _value in parse_qsl(parsed.query))
    except ValueError:
        return None
    if any(term in name for name in query_names for term in sensitive_query_terms):
        return None
    return candidate


def _safe_endpoint(value: object) -> str:
    """Keep only a printable endpoint path; never retain query credentials."""

    if not isinstance(value, str):
        return "/detailCommon2"
    try:
        path = urlsplit(value).path
    except ValueError:
        return "/detailCommon2"
    path = "".join(character for character in path if ord(character) >= 32).strip()
    return path or "/detailCommon2"


def _provider_language(client: TourDetailClient) -> str:
    language = getattr(client, "language", "")
    if isinstance(language, str) and language in ALLOWED_LANGUAGES:
        return language
    return "unknown"


def _finite_coordinate(
    value: Decimal | None,
    *,
    lower: float,
    upper: float,
) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(converted) or not lower <= converted <= upper:
        return None
    return converted


def _combined_address(detail: TourPlaceDetail) -> str:
    parts: list[str] = []
    for raw_part in (detail.address, detail.detail_address):
        part = sanitize_provider_html(raw_part)
        if part and not any(part == existing or part in existing for existing in parts):
            parts.append(part)
    return " ".join(parts)


def _bounded_model_text(spot: WaterSpot, field_name: str, value: str) -> str | None:
    if not value:
        return None
    maximum = spot._meta.get_field(field_name).max_length
    if maximum is not None and len(value) > maximum:
        return None
    return value


def _incoming_values(
    spot: WaterSpot,
    detail: TourPlaceDetail,
) -> dict[str, str | float | None]:
    image = _safe_https_image_url(detail.image_url)
    if image is None:
        image = _safe_https_image_url(detail.thumbnail_url)
    return {
        "name": _bounded_model_text(
            spot,
            "name",
            sanitize_provider_html(detail.title),
        ),
        "address": _bounded_model_text(
            spot,
            "address",
            _combined_address(detail),
        ),
        "lat": _finite_coordinate(detail.latitude, lower=-90.0, upper=90.0),
        "lng": _finite_coordinate(detail.longitude, lower=-180.0, upper=180.0),
        "image_url": _bounded_model_text(spot, "image_url", image or ""),
        "description": sanitize_provider_html(detail.overview) or None,
    }


def _field_is_empty(field_name: str, value: object) -> bool:
    if field_name in {"lat", "lng"}:
        # The existing non-null model uses zero as its legacy "not geocoded"
        # placeholder. TourAPI describes Korean POIs, so zero is not a valid
        # curated coordinate for this enrichment boundary.
        return value is None or value == 0 or value == 0.0
    return value is None or not str(value).strip()


def _changed_values(
    spot: WaterSpot,
    detail: TourPlaceDetail,
    *,
    overwrite: bool,
) -> dict[str, str | float]:
    changes: dict[str, str | float] = {}
    incoming = _incoming_values(spot, detail)
    for field_name in FIELD_ORDER:
        value = incoming[field_name]
        if value is None:
            continue
        current = getattr(spot, field_name)
        if current == value:
            continue
        if overwrite or _field_is_empty(field_name, current):
            changes[field_name] = value
    return changes


def _catalog_provenance_values(
    provenance: TourSourceProvenance,
) -> dict[str, str | datetime | None]:
    verified_at = provenance.provider_modified_at
    if verified_at is not None and timezone.is_naive(verified_at):
        raise CatalogEnrichmentError(
            "TourAPI returned a provider modification time without a timezone"
        )
    verification = (
        WaterSpot.VerificationState.VERIFIED
        if verified_at is not None
        else WaterSpot.VerificationState.PARTIAL
    )
    return {
        "catalog_source": provenance.provider,
        "catalog_source_url": provenance.public_source_url,
        # The upstream modifiedtime is deterministic, unlike the local command
        # clock, so replaying identical provider evidence remains idempotent.
        "catalog_verified_at": verified_at,
        "catalog_verification": verification,
    }


def _catalog_provenance_changes(
    spot: WaterSpot,
    provenance: TourSourceProvenance,
) -> dict[str, str | datetime | None]:
    incoming = _catalog_provenance_values(provenance)
    return {
        field_name: value
        for field_name, value in incoming.items()
        if getattr(spot, field_name) != value
    }


class TourSpotEnrichmentService:
    """Fetch verified details, then atomically enrich existing curated rows."""

    def __init__(self, client: TourDetailClient) -> None:
        self._client = client

    def sync(
        self,
        spots: Iterable[WaterSpot],
        *,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> TourEnrichmentReport:
        if not isinstance(overwrite, bool) or not isinstance(dry_run, bool):
            raise TypeError("overwrite and dry_run must be booleans")
        ordered_spots = self._normalize_spots(spots)
        prepared: list[_PreparedEnrichment] = []
        skipped: list[SpotEnrichmentResult] = []
        detail_cache: dict[str, tuple[TourPlaceDetail, TourSourceProvenance]] = {}

        # All remote work and content-id validation completes before any write.
        for spot in ordered_spots:
            content_id = spot.tourapi_id.strip()
            if not content_id:
                skipped.append(
                    SpotEnrichmentResult(
                        spot_id=spot.pk,
                        status="skipped_missing_tourapi_id",
                        changed_fields=(),
                        provenance=None,
                    )
                )
                continue
            cached = detail_cache.get(content_id)
            if cached is None:
                result = self._client.fetch_detail(content_id)
                detail, provenance = self._validated_detail(
                    content_id,
                    result,
                    spot.pk,
                )
                detail_cache[content_id] = (detail, provenance)
            else:
                detail, provenance = cached
            prepared.append(
                _PreparedEnrichment(
                    spot_id=spot.pk,
                    expected_content_id=content_id,
                    detail=detail,
                    provenance=provenance,
                )
            )

        if dry_run:
            spots_by_id = {spot.pk: spot for spot in ordered_spots}
            evaluated = tuple(
                self._result_for(
                    spots_by_id[item.spot_id],
                    item,
                    overwrite=overwrite,
                    dry_run=True,
                    apply=False,
                )
                for item in prepared
            )
            return self._report(
                (*skipped, *evaluated),
                dry_run=True,
                overwrite=overwrite,
            )

        persisted: list[SpotEnrichmentResult] = []
        if prepared:
            with transaction.atomic():
                spot_ids = tuple(item.spot_id for item in prepared)
                locked = {
                    spot.pk: spot
                    for spot in WaterSpot.objects.select_for_update()
                    .filter(pk__in=spot_ids)
                    .order_by("pk")
                }
                if len(locked) != len(set(spot_ids)):
                    raise CatalogEnrichmentError(
                        "A curated WaterSpot disappeared during TourAPI synchronization"
                    )
                for item in prepared:
                    spot = locked[item.spot_id]
                    if spot.tourapi_id.strip() != item.expected_content_id:
                        raise CatalogEnrichmentError(
                            "A curated WaterSpot TourAPI id changed during synchronization"
                        )
                    persisted.append(
                        self._result_for(
                            spot,
                            item,
                            overwrite=overwrite,
                            dry_run=False,
                            apply=True,
                        )
                    )
        return self._report((*skipped, *persisted), dry_run=False, overwrite=overwrite)

    @staticmethod
    def _normalize_spots(spots: Iterable[WaterSpot]) -> tuple[WaterSpot, ...]:
        unique: dict[int, WaterSpot] = {}
        for spot in spots:
            if not isinstance(spot, WaterSpot) or spot.pk is None:
                raise CatalogEnrichmentError(
                    "TourAPI enrichment requires saved WaterSpot rows"
                )
            unique[spot.pk] = spot
        ordered = tuple(unique[spot_id] for spot_id in sorted(unique))
        seen_content_ids: set[str] = set()
        for spot in ordered:
            content_id = spot.tourapi_id.strip()
            if content_id and content_id in seen_content_ids:
                raise CatalogEnrichmentError(
                    "Duplicate curated WaterSpot TourAPI ids require a manual "
                    "identifier audit before synchronization"
                )
            if content_id:
                seen_content_ids.add(content_id)
        return ordered

    def _validated_detail(
        self,
        expected_content_id: str,
        result: ProviderResult[TourPlaceDetail],
        spot_id: int,
    ) -> tuple[TourPlaceDetail, TourSourceProvenance]:
        if not isinstance(result, ProviderResult) or len(result.records) != 1:
            raise CatalogEnrichmentError(
                f"TourAPI did not return exactly one detail for WaterSpot {spot_id}"
            )
        detail = result.records[0]
        if not isinstance(detail, TourPlaceDetail):
            raise CatalogEnrichmentError(
                f"TourAPI returned an unexpected detail type for WaterSpot {spot_id}"
            )
        if detail.content_id.strip() != expected_content_id:
            raise CatalogEnrichmentError(
                f"TourAPI returned a different content id for WaterSpot {spot_id}"
            )
        if detail.modified_at is not None and (
            not isinstance(detail.modified_at, datetime)
            or timezone.is_naive(detail.modified_at)
        ):
            raise CatalogEnrichmentError(
                f"TourAPI returned an invalid modification time for WaterSpot {spot_id}"
            )
        provenance = TourSourceProvenance(
            provider="TourAPI",
            public_source_url=TourApiClient.SOURCE_URL,
            endpoint=_safe_endpoint(result.endpoint),
            content_id=expected_content_id,
            language=_provider_language(self._client),
            provider_modified_at=detail.modified_at,
        )
        return detail, provenance

    @staticmethod
    def _result_for(
        spot: WaterSpot,
        prepared: _PreparedEnrichment,
        *,
        overwrite: bool,
        dry_run: bool,
        apply: bool,
    ) -> SpotEnrichmentResult:
        changes: dict[str, str | float | datetime | None] = dict(
            _changed_values(spot, prepared.detail, overwrite=overwrite)
        )
        changes.update(_catalog_provenance_changes(spot, prepared.provenance))
        changed_fields = tuple(
            field_name
            for field_name in (*FIELD_ORDER, *PROVENANCE_FIELD_ORDER)
            if field_name in changes
        )
        if apply and changed_fields:
            for field_name in changed_fields:
                setattr(spot, field_name, changes[field_name])
            spot.save(update_fields=changed_fields)
        if changed_fields:
            status = "would_update" if dry_run else "updated"
        else:
            status = "unchanged"
        return SpotEnrichmentResult(
            spot_id=spot.pk,
            status=status,
            changed_fields=changed_fields,
            provenance=prepared.provenance,
        )

    @staticmethod
    def _report(
        results: Iterable[SpotEnrichmentResult],
        *,
        dry_run: bool,
        overwrite: bool,
    ) -> TourEnrichmentReport:
        ordered = tuple(sorted(results, key=lambda result: result.spot_id))
        return TourEnrichmentReport(
            results=ordered,
            dry_run=dry_run,
            overwrite=overwrite,
        )
