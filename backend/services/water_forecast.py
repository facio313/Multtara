"""
Water Forecast (A2).

Builds D+1..D+7 predicted Water Index from the latest condition.
Public forecast APIs are not wired yet, so day-to-day deltas are deterministic
per spot (stable demo) rather than live 중기예보.
"""

from __future__ import annotations

import hashlib
from copy import copy
from datetime import timedelta

from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.forecasts.models import WaterForecast
from apps.spots.models import WaterSpot
from services.water_index import calculate_water_index, default_activity_for_spot


def _unit(spot_id: int, day: int) -> float:
    digest = hashlib.md5(f"{spot_id}:{day}".encode(), usedforsecurity=False).hexdigest()
    return int(digest[:4], 16) / 65535.0


def _projected_condition(condition: WaterCondition, day: int, spot_id: int) -> WaterCondition:
    projected = copy(condition)
    unit = _unit(spot_id, day)
    temp_shift = (unit - 0.5) * 6
    rain = 0.0 if unit > 0.35 else (1 - unit) * 25
    wave_shift = (unit - 0.5) * 0.6
    projected.air_temp = None if condition.air_temp is None else condition.air_temp + temp_shift
    projected.water_temp = (
        None if condition.water_temp is None else condition.water_temp + temp_shift * 0.4
    )
    projected.rainfall_recent = rain
    projected.wave_height = (
        None if condition.wave_height is None else max(0.05, condition.wave_height + wave_shift)
    )
    projected.wind_speed = (
        None if condition.wind_speed is None else max(0.2, condition.wind_speed + (unit - 0.5) * 4)
    )
    return projected


def upsert_forecast_for_spot(spot: WaterSpot, days: int = 7) -> list[WaterForecast]:
    condition = WaterCondition.objects.filter(spot=spot).order_by("-fetched_at").first()
    if condition is None:
        return []

    activity = default_activity_for_spot(spot)
    today = timezone.localdate()
    now = timezone.now()
    written: list[WaterForecast] = []

    for day in range(1, days + 1):
        forecast_date = today + timedelta(days=day)
        projected = _projected_condition(condition, day, spot.id)
        weekday = forecast_date.weekday()
        weekend_bonus = 6 if weekday >= 5 else 0
        index = calculate_water_index(projected, activity, spot_type=spot.type)
        index = max(0, min(100, index + weekend_bonus))
        factors = {
            "activity": activity,
            "air_temp": projected.air_temp,
            "water_temp": projected.water_temp,
            "rainfall_recent": projected.rainfall_recent,
            "wave_height": projected.wave_height,
            "wind_speed": projected.wind_speed,
            "weekend_bonus": weekend_bonus,
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
