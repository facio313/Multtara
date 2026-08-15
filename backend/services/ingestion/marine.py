"""KHOA collection, matching, evaluation, and persistence orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Iterable, Sequence

from django.utils import timezone

from services.providers.base import ProviderResult
from services.providers.khoa import KhoaClient
from services.water_index import (
    Activity,
    EvaluationContext,
    IndexResult,
    SafetyStatus,
    evaluate_water_index,
)

from .khoa_adapter import (
    AdaptedKhoaObservation,
    adapt_beach_forecast,
    adapt_mudflat_forecast,
    adapt_rip_current_forecast,
    adapt_surf_forecast,
)
from .persistence import PersistenceResult, persist_evaluation


SUPPORTED_ACTIVITIES = (Activity.SWIM, Activity.SURF, Activity.MUDFLAT)


@dataclass(frozen=True, slots=True)
class SyncActivityReport:
    activity: Activity
    fetched_records: int
    matched_records: int
    persisted_records: int
    created_snapshots: int
    created_scores: int
    skipped_records: int
    unknown_results: int


@dataclass(frozen=True, slots=True)
class SyncReport:
    activities: tuple[SyncActivityReport, ...]
    dry_run: bool

    @property
    def fetched_records(self) -> int:
        return sum(item.fetched_records for item in self.activities)

    @property
    def matched_records(self) -> int:
        return sum(item.matched_records for item in self.activities)

    @property
    def persisted_records(self) -> int:
        return sum(item.persisted_records for item in self.activities)


class MarineIngestionService:
    """Collect KHOA activity records and evaluate matched local water spots."""

    def __init__(
        self,
        client: KhoaClient,
        *,
        evaluator: Callable[[Any, EvaluationContext], IndexResult] = evaluate_water_index,
        persister: Callable[..., PersistenceResult] = persist_evaluation,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        self._client = client
        self._evaluator = evaluator
        self._persister = persister
        self._clock = clock

    def sync(
        self,
        *,
        activities: Iterable[Activity | str],
        request_date: date,
        spots: Sequence[Any],
        dry_run: bool = False,
    ) -> SyncReport:
        normalized = _normalize_activities(activities)
        fetched_at = self._clock()
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("ingestion clock must return a timezone-aware datetime")
        reports = tuple(
            self._sync_activity(
                activity=activity,
                request_date=request_date,
                spots=spots,
                dry_run=dry_run,
                fetched_at=fetched_at,
            )
            for activity in normalized
        )
        return SyncReport(activities=reports, dry_run=dry_run)

    def evaluate_for_spot(
        self,
        *,
        spot: Any,
        observation: AdaptedKhoaObservation,
        dry_run: bool,
    ) -> tuple[IndexResult, PersistenceResult | None]:
        """Evaluate one already-adapted observation and optionally persist it."""

        participant_profile = (
            "family" if observation.activity is Activity.SWIM else "general"
        )
        result = self._evaluator(
            observation.observations,
            EvaluationContext(
                activity=observation.activity,
                at=observation.evaluation_at,
                participant_profile=participant_profile,
            ),
        )
        if dry_run:
            return result, None
        persisted = self._persister(
            spot=spot,
            observation=observation,
            result=result,
            participant_profile=participant_profile,
        )
        return result, persisted

    def _sync_activity(
        self,
        *,
        activity: Activity,
        request_date: date,
        spots: Sequence[Any],
        dry_run: bool,
        fetched_at: datetime,
    ) -> SyncActivityReport:
        provider_result, adapter = self._fetch(activity, request_date)
        matched = persisted = created_snapshots = created_scores = unknown = 0
        skipped = 0
        fetched_records = len(provider_result.records)
        seen: set[tuple[Any, str]] = set()

        for record in provider_result.records:
            observation = adapter(
                record,
                fetched_at=fetched_at,
                endpoint=provider_result.endpoint,
            )
            spot = match_observation_to_spot(observation, spots)
            if spot is None:
                skipped += 1
                continue
            deduplication_key = (getattr(spot, "pk", id(spot)), observation.provider_record_id)
            if deduplication_key in seen:
                skipped += 1
                continue
            seen.add(deduplication_key)
            matched += 1
            result, persistence_result = self.evaluate_for_spot(
                spot=spot,
                observation=observation,
                dry_run=dry_run,
            )
            if result.safety_status is SafetyStatus.UNKNOWN:
                unknown += 1
            if persistence_result is not None:
                persisted += 1
                created_snapshots += int(persistence_result.snapshot_created)
                created_scores += int(persistence_result.score_created)

        # Rip-current observations require a curated official beach code. We
        # never infer it from TourAPI ids, names, or coordinates.
        if activity is Activity.SWIM:
            for spot in spots:
                beach_code = str(
                    getattr(spot, "khoa_beach_code", "") or ""
                ).strip()
                if not beach_code or not _spot_supports_activity(spot, Activity.SWIM):
                    continue
                rip_result = self._client.fetch_rip_current_forecasts(
                    beach_code=beach_code,
                    request_date=request_date,
                )
                fetched_records += len(rip_result.records)
                for record in rip_result.records:
                    record_code = str(getattr(record, "beach_code", "") or "").strip()
                    if record_code.casefold() != beach_code.casefold():
                        skipped += 1
                        continue
                    observation = adapt_rip_current_forecast(
                        record,
                        fetched_at=fetched_at,
                        endpoint=rip_result.endpoint,
                    )
                    if not _observation_matches_configured_spot(observation, spot):
                        skipped += 1
                        continue
                    deduplication_key = (
                        getattr(spot, "pk", id(spot)),
                        observation.provider_record_id,
                    )
                    if deduplication_key in seen:
                        skipped += 1
                        continue
                    seen.add(deduplication_key)
                    matched += 1
                    result, persistence_result = self.evaluate_for_spot(
                        spot=spot,
                        observation=observation,
                        dry_run=dry_run,
                    )
                    if result.safety_status is SafetyStatus.UNKNOWN:
                        unknown += 1
                    if persistence_result is not None:
                        persisted += 1
                        created_snapshots += int(persistence_result.snapshot_created)
                        created_scores += int(persistence_result.score_created)

        return SyncActivityReport(
            activity=activity,
            fetched_records=fetched_records,
            matched_records=matched,
            persisted_records=persisted,
            created_snapshots=created_snapshots,
            created_scores=created_scores,
            skipped_records=skipped,
            unknown_results=unknown,
        )

    def _fetch(
        self, activity: Activity, request_date: date
    ) -> tuple[ProviderResult[Any], Callable[..., AdaptedKhoaObservation]]:
        if activity is Activity.SWIM:
            return (
                self._client.fetch_beach_forecasts(request_date=request_date),
                adapt_beach_forecast,
            )
        if activity is Activity.SURF:
            return (
                self._client.fetch_surf_forecasts(request_date=request_date),
                adapt_surf_forecast,
            )
        if activity is Activity.MUDFLAT:
            return (
                self._client.fetch_mudflat_forecasts(request_date=request_date),
                adapt_mudflat_forecast,
            )
        raise ValueError(f"unsupported KHOA ingestion activity: {activity.value}")


def match_observation_to_spot(
    observation: AdaptedKhoaObservation,
    spots: Sequence[Any],
    *,
    maximum_distance_km: float = 5.0,
) -> Any | None:
    """Match a provider identity, using coordinates only as corroboration."""

    compatible = [
        spot for spot in spots if _spot_supports_activity(spot, observation.activity)
    ]
    provider_name = _canonical_place_name(observation.place_name)
    if not provider_name:
        return None
    exact = [
        spot
        for spot in compatible
        if _canonical_place_name(getattr(spot, "name", None)) == provider_name
    ]
    if not exact:
        return None
    if observation.latitude is None or observation.longitude is None:
        return exact[0] if len(exact) == 1 else None
    return _nearest(observation, exact, maximum_distance_km)


def _normalize_activities(values: Iterable[Activity | str]) -> tuple[Activity, ...]:
    result: list[Activity] = []
    for value in values:
        activity = value if isinstance(value, Activity) else Activity(str(value))
        if activity not in SUPPORTED_ACTIVITIES:
            raise ValueError(f"unsupported KHOA ingestion activity: {activity.value}")
        if activity not in result:
            result.append(activity)
    if not result:
        raise ValueError("at least one activity is required")
    return tuple(result)


def _spot_supports_activity(spot: Any, activity: Activity) -> bool:
    spot_type = str(getattr(spot, "type", "")).strip().lower()
    if activity in {Activity.SWIM, Activity.SURF}:
        return spot_type in {"beach", "sea", "marine_beach"}
    if activity is Activity.MUDFLAT:
        return spot_type in {"beach", "sea", "mudflat", "tidal_flat"}
    return False


def _canonical_place_name(value: str | None) -> str:
    if not value:
        return ""
    canonical = "".join(character for character in value.casefold() if character.isalnum())
    for suffix in ("갯벌체험마을", "해수욕장", "해변", "비치", "갯벌"):
        if canonical.endswith(suffix) and len(canonical) > len(suffix):
            canonical = canonical[: -len(suffix)]
            break
    return canonical


def _nearest(
    observation: AdaptedKhoaObservation,
    spots: Sequence[Any],
    maximum_distance_km: float,
) -> Any | None:
    if observation.latitude is None or observation.longitude is None:
        return None
    candidates: list[tuple[float, Any]] = []
    for spot in spots:
        latitude = _finite_float(getattr(spot, "lat", None))
        longitude = _finite_float(getattr(spot, "lng", None))
        if latitude is None or longitude is None:
            continue
        distance = _haversine_km(
            observation.latitude,
            observation.longitude,
            latitude,
            longitude,
        )
        if distance <= maximum_distance_km:
            candidates.append((distance, spot))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], str(getattr(item[1], "pk", ""))))
    return candidates[0][1]


def _observation_matches_configured_spot(
    observation: AdaptedKhoaObservation,
    spot: Any,
    *,
    maximum_distance_km: float = 5.0,
) -> bool:
    """Reject a curated-code response whose coordinates contradict the spot."""

    if observation.latitude is None or observation.longitude is None:
        return True
    latitude = _finite_float(getattr(spot, "lat", None))
    longitude = _finite_float(getattr(spot, "lng", None))
    if latitude is None or longitude is None:
        return False
    return (
        _haversine_km(
            observation.latitude,
            observation.longitude,
            latitude,
            longitude,
        )
        <= maximum_distance_km
    )


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    term = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(term), math.sqrt(1 - term))
