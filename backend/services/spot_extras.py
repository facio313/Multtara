"""Code-only extras: facilities, catch, onsen, crowd, and quality trust."""

from __future__ import annotations

from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.spots.models import CatchGuide, HotspringDetail, NearbyFacility, WaterSpot
from apps.users.models import UserActivity
from services.asmr_score import asmr_payload
from services.golden_moment import approximate_sunset, golden_moments
from services.spot_analytics import analytics_payload

__all__ = [
    "analytics_payload",
    "approximate_sunset",
    "asmr_payload",
    "catch_payload",
    "estimate_crowd",
    "facilities_payload",
    "golden_moments",
    "hotspring_payload",
    "quality_trust",
    "seed_spot_extras",
]

FACILITY_LABELS = {
    "shower": "샤워장",
    "changing_room": "탈의실",
    "restaurant": "식당",
    "lodging": "숙소",
    "parking": "주차장",
    "local_food": "로컬 맛집",
}

DEFAULT_FACILITIES = {
    "sea": (
        ("shower", "공용 샤워장", 3),
        ("changing_room", "탈의실", 3),
        ("local_food", "해변 포차", 8),
        ("parking", "공영 주차장", 5),
    ),
    "valley": (
        ("parking", "계곡 주차장", 8),
        ("local_food", "계곡 백숙", 12),
    ),
    "hotspring": (
        ("changing_room", "온천 탈의실", 1),
        ("local_food", "온천수빵", 5),
        ("lodging", "온천 여관", 10),
    ),
    "tidal_flat": (
        ("parking", "갯벌 주차장", 6),
        ("local_food", "조개구이", 10),
    ),
    "waterfall": (("parking", "폭포 주차장", 10),),
    "lake": (("parking", "호수 주차장", 8), ("local_food", "호반 식당", 12)),
    "riverside": (("parking", "강변 주차장", 8),),
    "waterpark": (("shower", "파크 샤워장", 1), ("changing_room", "탈의실", 1)),
    "pool": (("shower", "수영장 샤워", 1),),
}

DEFAULT_CATCH = {
    "species": "바지락, 고둥, 칠게",
    "banned_species": "보호종 · 어린 개체",
    "best_time": "간조 전후 2시간",
    "season_restriction": "산란기 채집 금지 안내를 따르세요.",
}

DEFAULT_HOTSPRING = {
    "minerals": "나트륨, 탄산, 황",
    "benefits": "피부, 피로, 신경통",
}


def _latest_condition(spot: WaterSpot) -> WaterCondition | None:
    cache = getattr(spot, "_prefetched_objects_cache", None)
    if cache is not None and "conditions" in cache:
        return next(iter(spot.conditions.all()), None)
    return spot.conditions.order_by("-fetched_at").first()


def facilities_payload(spot: WaterSpot) -> list[dict]:
    rows = list(spot.nearbyfacility_set.all()) if hasattr(spot, "nearbyfacility_set") else []
    if rows:
        return [
            {
                "type": row.type,
                "label": FACILITY_LABELS.get(row.type, row.type),
                "name": row.name,
                "tag": row.tag,
                "distance_min": row.distance_min,
            }
            for row in rows
        ]
    defaults = DEFAULT_FACILITIES.get(spot.type, (("parking", "주차장", 8),))
    return [
        {
            "type": kind,
            "label": FACILITY_LABELS.get(kind, kind),
            "name": name,
            "tag": "",
            "distance_min": minutes,
        }
        for kind, name, minutes in defaults
    ]


def catch_payload(spot: WaterSpot) -> dict | None:
    if spot.type != "tidal_flat":
        row = spot.catchguide_set.first() if hasattr(spot, "catchguide_set") else None
        if row is None:
            return None
    else:
        row = spot.catchguide_set.first() if hasattr(spot, "catchguide_set") else None
    data = {
        "species": getattr(row, "species", None) or DEFAULT_CATCH["species"],
        "banned_species": getattr(row, "banned_species", None) or DEFAULT_CATCH["banned_species"],
        "best_time": getattr(row, "best_time", None) or DEFAULT_CATCH["best_time"],
        "season_restriction": getattr(row, "season_restriction", None)
        or DEFAULT_CATCH["season_restriction"],
    }
    return data if spot.type == "tidal_flat" or row else None


def hotspring_payload(spot: WaterSpot) -> dict | None:
    if spot.type != "hotspring":
        return None
    try:
        detail = spot.hotspringdetail
    except HotspringDetail.DoesNotExist:
        detail = None
    return {
        "minerals": (detail.minerals if detail and detail.minerals else DEFAULT_HOTSPRING["minerals"]),
        "benefits": (detail.benefits if detail and detail.benefits else DEFAULT_HOTSPRING["benefits"]),
    }


def estimate_crowd(spot: WaterSpot, stored: dict | None = None) -> dict:
    if stored and stored.get("predicted_level"):
        return stored
    now = timezone.localtime()
    weekend = now.weekday() >= 5
    hour = now.hour
    if weekend and 11 <= hour <= 17:
        level, rec, parking = "high", "이른 오전", "혼잡"
    elif 11 <= hour <= 16:
        level, rec, parking = "medium", "오전 9-11시", "보통"
    else:
        level, rec, parking = "low", "지금", "여유"
    return {
        "predicted_level": level,
        "recommended_time": rec,
        "parking_availability": parking,
        "source": "estimated",
    }


def quality_trust(spot: WaterSpot) -> dict:
    condition = _latest_condition(spot)
    official = getattr(condition, "water_quality_grade", "") or ""
    reviews = UserActivity.objects.filter(spot=spot, action="visited").exclude(review_text="")
    dirty = 0
    clean = 0
    for row in reviews:
        text = row.review_text
        if any(token in text for token in ("탁", "더럽", "냄새", "거품")):
            dirty += 1
        if any(token in text for token in ("맑", "깨끗", "투명")):
            clean += 1
    if dirty and dirty > clean:
        crowd = "나쁨 쪽 후기"
        agree = official in {"3", "4"}
    elif clean and clean >= dirty:
        crowd = "맑음 쪽 후기"
        agree = official in {"1", "2", ""}
    else:
        crowd = "후기 부족"
        agree = None
    return {
        "official_grade": official or None,
        "review_signal": crowd,
        "review_count": reviews.count(),
        "agrees_with_official": agree,
    }


def seed_spot_extras(spot: WaterSpot) -> None:
    if not NearbyFacility.objects.filter(spot=spot).exists():
        for kind, name, minutes in DEFAULT_FACILITIES.get(spot.type, (("parking", "주차장", 8),)):
            NearbyFacility.objects.create(
                spot=spot,
                type=kind,
                name=name,
                lat=spot.lat,
                lng=spot.lng,
                tag="",
                distance_min=minutes,
            )
    if spot.type == "tidal_flat" and not CatchGuide.objects.filter(spot=spot).exists():
        CatchGuide.objects.create(spot=spot, **DEFAULT_CATCH)
    if spot.type == "hotspring" and not HotspringDetail.objects.filter(spot=spot).exists():
        HotspringDetail.objects.create(spot=spot, **DEFAULT_HOTSPRING)
