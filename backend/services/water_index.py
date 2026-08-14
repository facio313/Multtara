"""
Water Index (A1).

Weighted 0-100 score from a WaterCondition. Weights live in ACTIVITY_WEIGHTS
so they can be tuned without touching view code.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.conditions.models import ConditionScore, CrowdLevel, WaterCondition
from apps.spots.models import WaterSpot

ACTIVITIES = ("swim", "surf", "relax", "mudflat", "onsen", "rafting")

DEFAULT_ACTIVITY_BY_TYPE = {
    "sea": "swim",
    "pool": "swim",
    "hotspring": "onsen",
    "valley": "relax",
    "lake": "relax",
    "waterpark": "swim",
    "waterfall": "relax",
    "tidal_flat": "mudflat",
    "riverside": "rafting",
}

ACTIVITY_WEIGHTS = {
    "swim": {
        "air_temp": 0.15,
        "water_temp": 0.20,
        "wind_speed": 0.10,
        "wave_height": 0.15,
        "rainfall": 0.10,
        "water_quality": 0.10,
        "rip_current": 0.10,
        "uv_index": 0.05,
        "crowd": 0.05,
    },
    "surf": {
        "wave_height": 0.30,
        "wind_speed": 0.20,
        "water_temp": 0.10,
        "air_temp": 0.10,
        "rainfall": 0.10,
        "rip_current": 0.10,
        "uv_index": 0.05,
        "crowd": 0.05,
    },
    "relax": {
        "crowd": 0.25,
        "air_temp": 0.15,
        "rainfall": 0.15,
        "water_quality": 0.10,
        "wind_speed": 0.10,
        "uv_index": 0.10,
        "water_temp": 0.10,
        "wave_height": 0.05,
    },
    "mudflat": {
        "tide_optimal": 0.30,
        "water_temp": 0.15,
        "wind_speed": 0.15,
        "rainfall": 0.15,
        "air_temp": 0.10,
        "water_quality": 0.10,
        "crowd": 0.05,
    },
    "onsen": {
        "air_temp": 0.30,
        "crowd": 0.25,
        "rainfall": 0.15,
        "uv_index": 0.10,
        "water_quality": 0.10,
        "wind_speed": 0.10,
    },
    "rafting": {
        "water_level": 0.30,
        "rainfall": 0.25,
        "air_temp": 0.15,
        "wind_speed": 0.10,
        "water_quality": 0.10,
        "crowd": 0.10,
    },
}

SPOT_TYPE_FACTORS = {
    "sea": [
        "air_temp",
        "water_temp",
        "wind_speed",
        "wave_height",
        "rainfall",
        "water_quality",
        "rip_current",
        "uv_index",
        "crowd",
    ],
    "valley": ["rainfall", "air_temp", "water_quality", "water_temp", "crowd", "water_level"],
    "hotspring": ["air_temp", "crowd", "rainfall", "uv_index"],
    "tidal_flat": ["tide_optimal", "water_temp", "wind_speed", "rainfall", "air_temp"],
    "lake": ["air_temp", "water_temp", "rainfall", "crowd", "wind_speed"],
    "waterfall": ["rainfall", "air_temp", "crowd", "water_quality"],
    "riverside": ["water_level", "rainfall", "air_temp", "water_quality", "crowd"],
    "pool": ["air_temp", "water_temp", "uv_index", "crowd", "rainfall"],
    "waterpark": ["air_temp", "uv_index", "crowd", "rainfall"],
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _score_air_temp(temp: float | None, activity: str) -> float | None:
    if temp is None:
        return None
    if activity == "onsen":
        return _clamp(100 - (temp / 32.0) * 80)
    if 24 <= temp <= 32:
        return _clamp(100 - abs(temp - 28) * 8)
    if temp < 24:
        return _clamp(temp * 3.2)
    return _clamp(100 - (temp - 32) * 10)


def _score_water_temp(temp: float | None, activity: str) -> float | None:
    if temp is None:
        return None
    if activity == "onsen":
        return 70.0
    if 22 <= temp <= 28:
        return _clamp(100 - abs(temp - 25) * 6)
    if temp < 22:
        return _clamp((temp / 22.0) * 70)
    return _clamp(100 - (temp - 28) * 8)


def _score_wind(speed: float | None, activity: str) -> float | None:
    if speed is None:
        return None
    if activity == "surf":
        if 5 <= speed <= 12:
            return 92.0
        if speed < 5:
            return _clamp((speed / 5.0) * 70)
        return _clamp(92 - (speed - 12) * 8)
    return _clamp(100 - speed * 8)


def _score_wave(height: float | None, activity: str) -> float | None:
    if height is None:
        return None
    if activity == "surf":
        if 0.8 <= height <= 2.2:
            return _clamp(100 - abs(height - 1.5) * 30)
        if height < 0.8:
            return _clamp((height / 0.8) * 50)
        return _clamp(80 - (height - 2.2) * 40)
    return _clamp(100 - height * 50)


def _score_rainfall(mm: float | None, activity: str) -> float | None:
    if mm is None:
        return None
    if activity == "rafting":
        if 10 <= mm <= 40:
            return 90.0
        if mm < 10:
            return _clamp(50 + mm * 4)
        return _clamp(90 - (mm - 40) * 2)
    return _clamp(100 - mm * 5)


def _score_quality(grade: Any) -> float | None:
    if grade is None or grade == "":
        return None
    mapping = {
        "1": 100.0,
        "2": 75.0,
        "3": 45.0,
        "4": 20.0,
        "좋음": 100.0,
        "보통": 70.0,
        "나쁨": 30.0,
    }
    key = str(grade).strip()
    if key in mapping:
        return mapping[key]
    try:
        return {1: 100.0, 2: 75.0, 3: 45.0, 4: 20.0}.get(int(float(key)), 50.0)
    except (TypeError, ValueError):
        return 50.0


def _score_rip(risk: str | None) -> float | None:
    if not risk:
        return None
    token = str(risk).strip().lower()
    if token in {"none", "low", "safe", "없음", "낮음"}:
        return 100.0
    if token in {"medium", "moderate", "caution", "보통"}:
        return 55.0
    return 15.0


def _score_uv(uv: float | None) -> float | None:
    if uv is None:
        return None
    if uv <= 2:
        return 80.0
    if uv <= 7:
        return 90.0
    return _clamp(90 - (uv - 7) * 12)


def _score_crowd(level: str | None, activity: str) -> float | None:
    if not level:
        return None
    token = str(level).strip().lower()
    low_better = {
        "low": 100.0,
        "낮음": 100.0,
        "medium": 60.0,
        "보통": 60.0,
        "high": 25.0,
        "높음": 25.0,
    }
    score = low_better.get(token)
    if score is None:
        return None
    if activity == "surf":
        return 70.0 if token in {"medium", "보통"} else score
    return score


def _score_water_level(level: float | None, activity: str) -> float | None:
    if level is None:
        return None
    if activity == "rafting":
        if 1.2 <= level <= 3.0:
            return 95.0
        if level < 1.2:
            return _clamp((level / 1.2) * 70)
        return _clamp(95 - (level - 3.0) * 25)
    if level <= 2.5:
        return 90.0
    return _clamp(90 - (level - 2.5) * 30)


def _score_tide(tide_schedule: Any, activity: str) -> float | None:
    if activity != "mudflat":
        return None
    if not tide_schedule:
        return 50.0
    lows = tide_schedule.get("low_tide") if isinstance(tide_schedule, dict) else None
    if lows:
        return 88.0
    return 50.0


def _factor_scores(
    condition: WaterCondition,
    activity: str,
    crowd_level: str | None,
) -> dict[str, float]:
    values = {
        "air_temp": _score_air_temp(condition.air_temp, activity),
        "water_temp": _score_water_temp(condition.water_temp, activity),
        "wind_speed": _score_wind(condition.wind_speed, activity),
        "wave_height": _score_wave(condition.wave_height, activity),
        "rainfall": _score_rainfall(condition.rainfall_recent, activity),
        "water_quality": _score_quality(condition.water_quality_grade),
        "rip_current": _score_rip(condition.rip_current_risk),
        "uv_index": _score_uv(condition.uv_index),
        "crowd": _score_crowd(crowd_level, activity),
        "water_level": _score_water_level(condition.water_level, activity),
        "tide_optimal": _score_tide(condition.tide_schedule, activity),
    }
    return {key: value for key, value in values.items() if value is not None}


def calculate_water_index(
    condition: WaterCondition,
    activity: str,
    spot_type: str | None = None,
    crowd_level: str | None = None,
) -> int:
    if activity not in ACTIVITY_WEIGHTS:
        raise ValueError(f"Unknown activity: {activity}")

    weights = dict(ACTIVITY_WEIGHTS[activity])
    allowed = SPOT_TYPE_FACTORS.get(spot_type or "")
    if allowed:
        weights = {key: value for key, value in weights.items() if key in allowed}

    scores = _factor_scores(condition, activity, crowd_level)
    usable = {key: weights[key] for key in weights if key in scores}
    if not usable:
        return 50

    total_weight = sum(usable.values())
    weighted = sum(scores[key] * (weight / total_weight) for key, weight in usable.items())
    return int(round(_clamp(weighted)))


def default_activity_for_spot(spot: WaterSpot) -> str:
    return DEFAULT_ACTIVITY_BY_TYPE.get(spot.type, "swim")


def upsert_scores_for_spot(spot: WaterSpot, condition: WaterCondition | None = None) -> list[ConditionScore]:
    condition = condition or (
        WaterCondition.objects.filter(spot=spot).order_by("-fetched_at").first()
    )
    if condition is None:
        return []

    crowd = (
        CrowdLevel.objects.filter(spot=spot)
        .order_by("-updated_at")
        .values_list("predicted_level", flat=True)
        .first()
    )
    now = timezone.now()
    written: list[ConditionScore] = []
    for activity in ACTIVITIES:
        score = calculate_water_index(
            condition,
            activity,
            spot_type=spot.type,
            crowd_level=crowd,
        )
        obj, _created = ConditionScore.objects.update_or_create(
            spot=spot,
            activity=activity,
            defaults={"score": score, "computed_at": now},
        )
        written.append(obj)
    return written
