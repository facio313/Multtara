"""Persistence and request-time selection for expiring route matrices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from typing import Iterable

from django.db import transaction
from django.db.models import Q

from apps.trips.models import RouteMatrixEntry, RouteMatrixSnapshot
from services.providers.valhalla import RouteMatrixResult


@dataclass(frozen=True, slots=True)
class RouteEvidence:
    snapshot_ids: tuple[int, ...]
    providers: tuple[str, ...]
    valid_until: datetime | None
    source_urls: tuple[str, ...]
    available_pairs: int


class DatabaseTravelTimeProvider:
    """Immutable minute lookup built only from current persisted provider rows."""

    def __init__(
        self,
        lookup: dict[tuple[str, str], int],
        evidence: RouteEvidence,
    ) -> None:
        self._lookup = dict(lookup)
        self.evidence = evidence

    @classmethod
    def current(
        cls,
        *,
        spot_ids: Iterable[int],
        transport: str,
        at: datetime,
    ) -> "DatabaseTravelTimeProvider":
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("route lookup time must be timezone-aware")
        ids = tuple(sorted(set(int(item) for item in spot_ids)))
        rows = (
            RouteMatrixEntry.objects.select_related("snapshot")
            .filter(
                origin_spot_id__in=ids,
                destination_spot_id__in=ids,
                snapshot__transport=transport,
                snapshot__state=RouteMatrixSnapshot.State.LIVE,
                snapshot__observed_at__lte=at,
                snapshot__valid_until__gte=at,
            )
            .filter(
                Q(snapshot__provider=RouteMatrixSnapshot.Provider.VALHALLA)
                | Q(snapshot__provider=RouteMatrixSnapshot.Provider.OPERATOR)
            )
            .order_by(
                "origin_spot_id",
                "destination_spot_id",
                "-snapshot__observed_at",
                "-snapshot_id",
            )
        )
        lookup: dict[tuple[str, str], int] = {}
        selected_snapshots: dict[int, RouteMatrixSnapshot] = {}
        for row in rows:
            key = (str(row.origin_spot_id), str(row.destination_spot_id))
            if key in lookup:
                continue
            # Round upward: a route estimate must never look faster because of
            # minute conversion.
            lookup[key] = max(1, math.ceil(row.duration_seconds / 60))
            selected_snapshots[row.snapshot_id] = row.snapshot

        snapshots = tuple(
            sorted(selected_snapshots.values(), key=lambda item: item.pk)
        )
        valid_until = min(
            (item.valid_until for item in snapshots),
            default=None,
        )
        return cls(
            lookup,
            RouteEvidence(
                snapshot_ids=tuple(item.pk for item in snapshots),
                providers=tuple(sorted({item.provider for item in snapshots})),
                valid_until=valid_until,
                source_urls=tuple(sorted({item.source_url for item in snapshots})),
                available_pairs=len(lookup),
            ),
        )

    def minutes(self, origin_id: str, destination_id: str) -> int | None:
        if origin_id == destination_id:
            return 0
        return self._lookup.get((origin_id, destination_id))


@transaction.atomic
def persist_route_matrix(
    result: RouteMatrixResult,
    *,
    observed_at: datetime,
    fetched_at: datetime,
    valid_for: timedelta,
    spot_ids: Iterable[int],
) -> tuple[RouteMatrixSnapshot, bool]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("route observed_at must be timezone-aware")
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("route fetched_at must be timezone-aware")
    if observed_at > fetched_at:
        raise ValueError("route observed_at cannot be after fetched_at")
    if valid_for <= timedelta(0) or valid_for > timedelta(days=7):
        raise ValueError("route validity must be positive and at most seven days")

    normalized_ids = tuple(sorted(set(int(item) for item in spot_ids)))
    if len(normalized_ids) < 2:
        raise ValueError("route matrix requires at least two spots")
    if any(item < 1 for item in normalized_ids):
        raise ValueError("route spot ids must be positive")

    canonical_values = [
        {
            "origin": item.origin_spot_id,
            "destination": item.destination_spot_id,
            "seconds": item.duration_seconds,
            "metres": item.distance_metres,
        }
        for item in sorted(
            result.values,
            key=lambda item: (item.origin_spot_id, item.destination_spot_id),
        )
    ]
    spot_set_hash = sha256(
        json.dumps(normalized_ids, separators=(",", ":")).encode()
    ).hexdigest()
    provider_record_id = sha256(
        json.dumps(
            {
                "transport": result.transport,
                "observed_minute": observed_at.replace(
                    second=0, microsecond=0
                ).isoformat(),
                "spot_set": spot_set_hash,
                "values": canonical_values,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    snapshot, created = RouteMatrixSnapshot.objects.get_or_create(
        provider=result.provider,
        provider_record_id=provider_record_id,
        defaults={
            "transport": result.transport,
            "state": RouteMatrixSnapshot.State.LIVE,
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "valid_until": observed_at + valid_for,
            "source_url": result.source_url,
            "spot_set_hash": spot_set_hash,
        },
    )
    if not created:
        return snapshot, False

    allowed = set(normalized_ids)
    entries: list[RouteMatrixEntry] = []
    seen: set[tuple[int, int]] = set()
    for item in result.values:
        key = (item.origin_spot_id, item.destination_spot_id)
        if (
            item.origin_spot_id not in allowed
            or item.destination_spot_id not in allowed
            or item.origin_spot_id == item.destination_spot_id
            or key in seen
        ):
            raise ValueError("route result contains an invalid or duplicate pair")
        seen.add(key)
        entries.append(
            RouteMatrixEntry(
                snapshot=snapshot,
                origin_spot_id=item.origin_spot_id,
                destination_spot_id=item.destination_spot_id,
                duration_seconds=item.duration_seconds,
                distance_metres=item.distance_metres,
            )
        )
    RouteMatrixEntry.objects.bulk_create(entries)
    return snapshot, True
