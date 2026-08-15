"""Apply public API payloads onto stored WaterCondition / WaterSpot rows."""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from services.marine import fetch_marine_extras, fetch_tide_schedule, fetch_water_temperature
from services.public_data import PublicDataError
from services.stations import CACHE_TTL, khoa_obs_code, mid_land_id, mid_ta_id, moe_pt_no, uv_area_no
from services.tourapi import search_spot
from services.water_quality import fetch_water_quality
from services.weather import fetch_ultra_short_observation, fetch_uv_index, seven_day_outlook

CONDITION_FIELDS = {
    "air_temp",
    "water_temp",
    "wind_speed",
    "wave_height",
    "rainfall_recent",
    "tide_schedule",
    "uv_index",
    "water_quality_grade",
    "rip_current_risk",
    "marine_indices",
}


def working_condition(spot: WaterSpot) -> WaterCondition:
    latest = WaterCondition.objects.filter(spot=spot).order_by("-fetched_at").first()
    if latest is None:
        return WaterCondition(spot=spot)
    return latest


def apply_fields(condition: WaterCondition, fields: dict) -> list[str]:
    changed: list[str] = []
    for key, value in fields.items():
        if key not in CONDITION_FIELDS or value is None:
            continue
        if key == "tide_schedule":
            if not isinstance(value, dict):
                continue
            if not value.get("low_tide") and not value.get("high_tide"):
                continue
        if key == "water_quality_grade" and value == "":
            continue
        if key == "marine_indices":
            if not isinstance(value, dict) or not value:
                continue
        setattr(condition, key, value)
        changed.append(key)
    return changed


def save_condition(condition: WaterCondition, changed: list[str]) -> WaterCondition:
    if not changed and condition.pk:
        return condition
    condition.fetched_at = timezone.now()
    condition.save()
    return condition


def outlook_cache_key(spot: WaterSpot) -> str:
    return f"kma:outlook:{spot.id}"


def sync_weather(spot: WaterSpot, *, dry_run: bool = False) -> dict:
    observation = fetch_ultra_short_observation(spot.lat, spot.lng)
    outlook = seven_day_outlook(
        spot.lat,
        spot.lng,
        land_reg_id=mid_land_id(spot),
        ta_reg_id=mid_ta_id(spot),
    )
    errors: list[str] = []
    uv_index = None
    area = uv_area_no(spot)
    if area:
        try:
            uv_index = fetch_uv_index(area)
        except PublicDataError as exc:
            errors.append(str(exc))
    payload = {**observation, "uv_index": uv_index}
    if dry_run:
        return {"observation": payload, "outlook": outlook, "saved": False, "errors": errors}

    cache.set(outlook_cache_key(spot), outlook, CACHE_TTL["weather_forecast"])
    condition = working_condition(spot)
    changed = apply_fields(condition, payload)
    save_condition(condition, changed)
    return {
        "observation": payload,
        "outlook": outlook,
        "saved": True,
        "changed": changed,
        "errors": errors,
    }


def sync_marine(spot: WaterSpot, *, dry_run: bool = False) -> dict:
    obs_code = khoa_obs_code(spot)
    if not obs_code:
        return {"skipped": True, "reason": "no KHOA obs code"}

    errors: list[str] = []
    water_temp = None
    tide_schedule = None
    try:
        water_temp = fetch_water_temperature(obs_code)
    except PublicDataError as exc:
        errors.append(str(exc))
    try:
        tide_schedule = fetch_tide_schedule(obs_code)
    except PublicDataError as exc:
        errors.append(str(exc))

    extras: dict = {}
    try:
        extras = fetch_marine_extras(spot)
    except PublicDataError as exc:
        errors.append(str(exc))

    water_temp = water_temp if water_temp is not None else extras.get("water_temp")
    payload = {
        "water_temp": water_temp,
        "tide_schedule": tide_schedule,
        "wave_height": extras.get("wave_height"),
        "rip_current_risk": extras.get("rip_current_risk"),
        "marine_indices": extras.get("marine_indices"),
    }
    has_tide = bool(tide_schedule and (tide_schedule.get("low_tide") or tide_schedule.get("high_tide")))
    has_extra = any(payload.get(key) for key in ("wave_height", "rip_current_risk", "marine_indices"))
    if water_temp is None and not has_tide and not has_extra and errors:
        raise PublicDataError(errors[0])
    if dry_run:
        return {"obs_code": obs_code, **payload, "saved": False, "errors": errors}

    condition = working_condition(spot)
    changed = apply_fields(condition, payload)
    save_condition(condition, changed)
    return {"obs_code": obs_code, **payload, "saved": True, "changed": changed, "errors": errors}


def sync_quality(spot: WaterSpot, *, dry_run: bool = False) -> dict:
    pt_no = moe_pt_no(spot)
    if not pt_no:
        return {"skipped": True, "reason": "no MOE station"}
    payload = fetch_water_quality(pt_no)
    if dry_run:
        return {**payload, "saved": False}
    condition = working_condition(spot)
    changed = apply_fields(condition, {"water_quality_grade": payload.get("water_quality_grade")})
    save_condition(condition, changed)
    return {**payload, "saved": True, "changed": changed}


def sync_tour(spot: WaterSpot, *, dry_run: bool = False) -> dict:
    payload = search_spot(spot.name)
    if dry_run:
        return {**payload, "saved": False}

    if payload.get("tourapi_id"):
        spot.tourapi_id = payload["tourapi_id"]
    image = payload.get("image_url") or ""
    if image:
        spot.image_url = image
    overview = (payload.get("description") or "").strip()
    if overview:
        spot.description = overview
    spot.save()
    return {**payload, "saved": True}
