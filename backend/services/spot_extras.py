"""Code-only extras: facilities, catch, onsen, crowd, ASMR, golden tide, analytics."""

from __future__ import annotations

import math
from datetime import date, time
from typing import Any

from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.forecasts.models import WaterForecast
from apps.spots.models import CatchGuide, HotspringDetail, NearbyFacility, WaterSpot
from apps.users.models import UserActivity

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

SOUND_TYPE = {
    "sea": "wave",
    "tidal_flat": "tidal",
    "valley": "valley",
    "waterfall": "waterfall",
    "lake": "rain",
    "riverside": "valley",
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


def asmr_payload(spot: WaterSpot) -> dict:
    condition = _latest_condition(spot)
    sound = SOUND_TYPE.get(spot.type, "wave")
    wave = getattr(condition, "wave_height", None) or 0
    wind = getattr(condition, "wind_speed", None) or 0
    rain = getattr(condition, "rainfall_recent", None) or 0
    if sound == "wave":
        score = min(100, 40 + wave * 28 + wind * 4)
    elif sound == "valley":
        score = min(100, 55 + rain * 1.2)
    elif sound == "waterfall":
        score = min(100, 70 + rain * 0.8)
    else:
        score = min(100, 50 + wind * 3)
    return {"sound_type": sound, "asmr_score": round(score), "audio_url": ""}


def _parse_clock(value: Any) -> time | None:
    text = str(value or "").strip()
    if len(text) >= 4 and ":" in text:
        try:
            hour, minute = text.split(":")[:2]
            return time(int(hour), int(minute[:2]))
        except ValueError:
            return None
    return None


def approximate_sunset(lat: float, lng: float, day: date) -> time:
    n = day.timetuple().tm_yday
    decl = math.radians(23.44 * math.sin(math.radians((360 / 365) * (n - 81))))
    lat_r = math.radians(lat)
    cos_ha = -math.tan(lat_r) * math.tan(decl)
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))
    solar = 12 + ha / 15 - (lng / 15)
    kst = solar + 9
    kst = kst % 24
    hour = int(kst)
    minute = int((kst - hour) * 60)
    return time(hour, max(0, min(59, minute)))


def golden_moments(spot: WaterSpot, condition: WaterCondition | None = None) -> list[dict]:
    condition = condition or _latest_condition(spot)
    schedule = getattr(condition, "tide_schedule", None) or {}
    highs = schedule.get("high_tide") or []
    today = timezone.localdate()
    sunset = approximate_sunset(spot.lat, spot.lng, today)
    sunset_min = sunset.hour * 60 + sunset.minute
    rows = []
    for raw in highs:
        clock = _parse_clock(raw)
        if clock is None:
            continue
        delta = abs((clock.hour * 60 + clock.minute) - sunset_min)
        if delta <= 90:
            rows.append(
                {
                    "date": today.isoformat(),
                    "time": clock.strftime("%H:%M"),
                    "sunset": sunset.strftime("%H:%M"),
                    "type": "high_tide_sunset",
                    "label": "만조×일몰",
                }
            )
    if not rows and spot.type in {"sea", "tidal_flat", "lake"}:
        rows.append(
            {
                "date": today.isoformat(),
                "time": sunset.strftime("%H:%M"),
                "sunset": sunset.strftime("%H:%M"),
                "type": "sunset",
                "label": "일몰",
            }
        )
    return rows[:2]


def analytics_payload(spot: WaterSpot) -> dict:
    temps = [
        row.water_temp
        for row in WaterCondition.objects.filter(spot=spot).exclude(water_temp=None)[:60]
    ]
    grades = list(
        WaterCondition.objects.filter(spot=spot)
        .exclude(water_quality_grade="")
        .order_by("-fetched_at")
        .values_list("water_quality_grade", flat=True)[:8]
    )
    forecasts = list(
        WaterForecast.objects.filter(spot=spot).order_by("forecast_date").values_list(
            "forecast_date", "predicted_index"
        )
    )
    best_season = "여름" if spot.type in {"sea", "waterpark", "pool"} else "가을"
    if forecasts:
        best = max(forecasts, key=lambda item: item[1] or 0)
        month = best[0].month
        best_season = {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄", 6: "여름", 7: "여름", 8: "여름"}.get(
            month, "가을"
        )
    trend = ""
    if len(grades) >= 2 and grades[0] != grades[-1]:
        trend = "개선" if str(grades[0]) < str(grades[-1]) else "주의"
    elif grades:
        trend = "유지"
    avg = round(sum(temps) / len(temps), 1) if temps else None
    return {
        "avg_water_temp": avg,
        "quality_trend": trend,
        "crowd_trend": "주말 혼잡" if spot.type in {"sea", "waterpark"} else "보통",
        "best_season": best_season,
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
