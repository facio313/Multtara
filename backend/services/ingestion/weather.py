"""KMA collection and auditable weather-snapshot orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

from django.utils import timezone

from services.providers.kma import KmaClient, latlon_to_grid

from .kma_adapter import adapt_weather_values
from .persistence import (
    SnapshotPersistenceResult,
    persist_observation,
)


KST = ZoneInfo("Asia/Seoul")


class KmaMode(str, Enum):
    NOWCAST = "nowcast"
    ULTRA_SHORT = "ultra-short"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class WeatherSyncReport:
    mode: KmaMode
    requested_grids: int
    fetched_values: int
    normalized_snapshots: int
    persisted_snapshots: int
    created_snapshots: int
    dry_run: bool


class WeatherIngestionService:
    """Fetch each KMA grid once and attach its public values to local spots."""

    def __init__(
        self,
        client: KmaClient,
        *,
        persister: Callable[..., SnapshotPersistenceResult] = persist_observation,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        self._client = client
        self._persister = persister
        self._clock = clock

    def sync(
        self,
        *,
        mode: KmaMode | str,
        issued_at: datetime,
        spots: Sequence[Any],
        dry_run: bool = False,
    ) -> WeatherSyncReport:
        normalized_mode = mode if isinstance(mode, KmaMode) else KmaMode(str(mode))
        fetched_at = self._clock()
        _require_aware(fetched_at, "ingestion clock")
        _require_aware(issued_at, "issued_at")
        grouped = _spots_by_grid(spots)

        fetched_values = normalized_snapshots = persisted = created = 0
        for (grid_x, grid_y), grid_spots in sorted(grouped.items()):
            result = self._fetch(
                normalized_mode,
                issued_at=issued_at,
                grid_x=grid_x,
                grid_y=grid_y,
            )
            fetched_values += len(result.records)
            observations = adapt_weather_values(
                result.records,
                fetched_at=fetched_at,
                endpoint=result.endpoint,
                forecast=normalized_mode is not KmaMode.NOWCAST,
            )
            normalized_snapshots += len(observations) * len(grid_spots)
            if dry_run:
                continue
            for spot in grid_spots:
                for observation in observations:
                    outcome = self._persister(spot=spot, observation=observation)
                    persisted += 1
                    created += int(outcome.snapshot_created)

        return WeatherSyncReport(
            mode=normalized_mode,
            requested_grids=len(grouped),
            fetched_values=fetched_values,
            normalized_snapshots=normalized_snapshots,
            persisted_snapshots=persisted,
            created_snapshots=created,
            dry_run=dry_run,
        )

    def _fetch(
        self,
        mode: KmaMode,
        *,
        issued_at: datetime,
        grid_x: int,
        grid_y: int,
    ):
        kwargs = {
            "issued_at": issued_at,
            "grid_x": grid_x,
            "grid_y": grid_y,
        }
        if mode is KmaMode.NOWCAST:
            return self._client.fetch_nowcast(**kwargs)
        if mode is KmaMode.ULTRA_SHORT:
            return self._client.fetch_ultra_short_forecast(**kwargs)
        return self._client.fetch_short_forecast(**kwargs)


def latest_available_issue(mode: KmaMode | str, now: datetime) -> datetime:
    """Return a conservative base time after the documented publication lag."""

    normalized_mode = mode if isinstance(mode, KmaMode) else KmaMode(str(mode))
    _require_aware(now, "now")
    local = now.astimezone(KST)
    if normalized_mode is KmaMode.NOWCAST:
        candidate = local.replace(minute=0, second=0, microsecond=0)
        if local.minute < 40:
            candidate -= timedelta(hours=1)
        return candidate
    if normalized_mode is KmaMode.ULTRA_SHORT:
        candidate = local.replace(minute=30, second=0, microsecond=0)
        if local.minute < 45:
            candidate -= timedelta(hours=1)
        return candidate

    # Village forecasts are issued at 02/05/08/11/14/17/20/23 KST. A
    # 15-minute publication buffer avoids requesting a base that is not yet
    # available at the provider boundary.
    ready_before = local - timedelta(minutes=15)
    for offset in range(0, 2):
        day = (ready_before - timedelta(days=offset)).date()
        candidates = [
            datetime(day.year, day.month, day.day, hour, tzinfo=KST)
            for hour in (23, 20, 17, 14, 11, 8, 5, 2)
        ]
        for candidate in candidates:
            if candidate <= ready_before:
                return candidate
    raise ValueError("no KMA short-forecast issue time is available")


def _spots_by_grid(spots: Iterable[Any]) -> dict[tuple[int, int], list[Any]]:
    grouped: dict[tuple[int, int], list[Any]] = {}
    for spot in spots:
        grid = latlon_to_grid(getattr(spot, "lat", None), getattr(spot, "lng", None))
        grouped.setdefault((grid.x, grid.y), []).append(spot)
    return grouped


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
