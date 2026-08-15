"""
Water Forecast (A2).

Builds D+1..D+7 predicted Water Index from KMA short/mid outlook when present.
Without public forecast data, the latest stored condition is reused for each day.
"""

from __future__ import annotations

from copy import copy
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.forecasts.models import WaterForecast
from apps.spots.models import WaterSpot
from services.water_index import calculate_water_index, default_activity_for_spot


def _outlook_usable(rows: list[dict] | None) -> bool:
    if not rows:
        return False
    return any(
        row.get("air_temp") is not None
        or row.get("rainfall_recent") is not None
        or row.get("wind_speed") is not None
        or row.get("wave_height") is not None
        for row in rows
    )


def load_outlook(spot: WaterSpot) -> list[dict]:
    cached = cache.get(f"kma:outlook:{spot.id}")
    return cached if isinstance(cached, list) else []


def _project(condition: WaterCondition, row: dict | None) -> WaterCondition:
    projected = copy(condition)
    if not row:
        return projected
    if row.get("air_temp") is not None:
        projected.air_temp = row["air_temp"]
    if row.get("wind_speed") is not None:
        projected.wind_speed = row["wind_speed"]
    if row.get("wave_height") is not None:
        projected.wave_height = row["wave_height"]
    if row.get("rainfall_recent") is not None:
        projected.rainfall_recent = row["rainfall_recent"]
    return projected


def upsert_forecast_for_spot(
    spot: WaterSpot,
    days: int = 7,
    outlook: list[dict] | None = None,
) -> list[WaterForecast]:
    condition = WaterCondition.objects.filter(spot=spot).order_by("-fetched_at").first()
    if condition is None:
        return []

    rows = outlook if outlook is not None else load_outlook(spot)
    use_kma = _outlook_usable(rows)
    by_date = {}
    if use_kma:
        for row in rows:
            by_date[str(row.get("forecast_date"))] = row

    activity = default_activity_for_spot(spot)
    today = timezone.localdate()
    now = timezone.now()
    written: list[WaterForecast] = []

    for day in range(1, days + 1):
        forecast_date = today + timedelta(days=day)
        row = by_date.get(str(forecast_date)) if use_kma else None
        projected = _project(condition, row)
        index = calculate_water_index(projected, activity, spot_type=spot.type)
        factors = {
            "activity": activity,
            "source": "kma" if row else "stored",
            "air_temp": projected.air_temp,
            "water_temp": projected.water_temp,
            "rainfall_recent": projected.rainfall_recent,
            "wave_height": projected.wave_height,
            "wind_speed": projected.wind_speed,
        }
        obj, _created = WaterForecast.objects.update_or_create(
            spot=spot,
            forecast_date=forecast_date,
            defaults={
                "predicted_index": index,
                "predicted_factors": factors,
                "computed_at": now,
            },
        )
        written.append(obj)
    return written
