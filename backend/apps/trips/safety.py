"""Build an offline-ready safety card snapshot from live spot state."""

from __future__ import annotations

from apps.spots.models import NearbyFacility
from apps.users.stamps import haversine_km
from services.safety_radar import assess_safety
from services.tide_timer import summarize_tide

CONDITION_FIELDS = (
    "water_temp",
    "air_temp",
    "wind_speed",
    "wave_height",
    "water_quality_grade",
    "rainfall_recent",
    "water_level",
    "rip_current_risk",
    "uv_index",
    "weather_alert",
)

SAFETY_TOKENS = (
    "lifeguard",
    "hospital",
    "clinic",
    "police",
    "fire",
    "rescue",
    "safety",
    "구급",
    "병원",
    "경찰",
    "소방",
    "구조",
    "안전",
)


def _latest(manager, order_by: str):
    return manager.order_by(order_by).first()


def _condition_dict(condition) -> dict:
    if condition is None:
        return {}
    return {name: getattr(condition, name) for name in CONDITION_FIELDS}


def nearest_safety_facility(spot) -> str:
    rows = list(NearbyFacility.objects.filter(spot=spot))
    if not rows:
        return spot.address or ""

    def rank(row):
        kind = f"{row.type} {row.tag} {row.name}".lower()
        is_safety = any(token in kind for token in SAFETY_TOKENS)
        return (0 if is_safety else 1, haversine_km(spot.lat, spot.lng, row.lat, row.lng))

    best = min(rows, key=rank)
    meters = int(haversine_km(spot.lat, spot.lng, best.lat, best.lng) * 1000)
    label = best.name or best.type
    if meters:
        return f"{label} ({meters}m)"
    return label


def build_snapshot(spot) -> dict:
    condition = _latest(spot.conditions, "-fetched_at")
    crowd = _latest(spot.crowd_levels, "-updated_at")
    safety = assess_safety(spot.type, condition, crowd)
    tide = summarize_tide((getattr(condition, "tide_schedule", None) or {}) if condition else {})
    return {
        "spot": {
            "id": spot.id,
            "name": spot.name,
            "type": spot.type,
            "region": spot.region,
            "address": spot.address,
            "lat": spot.lat,
            "lng": spot.lng,
        },
        "safety": safety,
        "condition": _condition_dict(condition),
        "tide": tide,
        "emergency": "119",
    }


def card_payload(card) -> dict:
    snapshot = card.condition_snapshot or {}
    spot = snapshot.get("spot") or {
        "id": card.spot_id,
        "name": card.spot.name,
        "type": card.spot.type,
        "region": card.spot.region,
        "address": card.spot.address,
        "lat": card.spot.lat,
        "lng": card.spot.lng,
    }
    return {
        "id": card.id,
        "spot_id": card.spot_id,
        "created_at": card.created_at,
        "nearest_safety_facility": card.nearest_safety_facility,
        "risk_factors": card.risk_factors or [],
        "shared_with": card.shared_with or [],
        "condition_snapshot": snapshot,
        "spot": spot,
        "safety": snapshot.get("safety") or {},
        "emergency": snapshot.get("emergency") or "119",
    }
