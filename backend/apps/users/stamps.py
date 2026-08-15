"""Water Passport stamps, collection progress, and earned badges."""

from __future__ import annotations

import math

from django.db.models import Count

from apps.spots.models import WaterSpot
from .models import Passport

CHECKIN_RADIUS_KM = 5.0

COLLECTION_TYPES = (
    ("sea", "해수욕장"),
    ("valley", "계곡"),
    ("hotspring", "온천"),
    ("waterfall", "폭포"),
    ("tidal_flat", "갯벌"),
    ("lake", "호수"),
    ("riverside", "강변"),
)

BADGE_RULES = (
    ("first_dip", "첫 퐁당", "장소를 1곳 인증했습니다.", lambda counts: counts["total"] >= 1),
    ("water_traveler", "물의 여행자", "장소를 5곳 인증했습니다.", lambda counts: counts["total"] >= 5),
    ("collector", "물길 수집가", "장소를 10곳 인증했습니다.", lambda counts: counts["total"] >= 10),
    ("sea_1", "첫 입수", "바다를 1곳 인증했습니다.", lambda counts: counts["sea"] >= 1),
    ("sea_3", "바다 여행자", "바다를 3곳 인증했습니다.", lambda counts: counts["sea"] >= 3),
    ("sea_5", "바다 정복자", "바다를 5곳 인증했습니다.", lambda counts: counts["sea"] >= 5),
    ("valley_1", "계곡 첫걸음", "계곡을 1곳 인증했습니다.", lambda counts: counts["valley"] >= 1),
    ("valley_3", "계곡 여행자", "계곡을 3곳 인증했습니다.", lambda counts: counts["valley"] >= 3),
    ("hotspring_1", "온천 입문", "온천을 1곳 인증했습니다.", lambda counts: counts["hotspring"] >= 1),
    ("hotspring_3", "온천 마스터", "온천을 3곳 인증했습니다.", lambda counts: counts["hotspring"] >= 3),
    ("waterfall_1", "폭포 수집", "폭포를 1곳 인증했습니다.", lambda counts: counts["waterfall"] >= 1),
    ("tidal_1", "갯벌 체험", "갯벌을 1곳 인증했습니다.", lambda counts: counts["tidal_flat"] >= 1),
    ("eco_1", "첫 플로깅", "에코 액션을 1번 남겼습니다.", lambda counts: counts["eco"] >= 1),
    ("eco_3", "물길 지킴이", "에코 액션을 3번 남겼습니다.", lambda counts: counts["eco"] >= 3),
)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def within_checkin_range(spot: WaterSpot, lat: float, lng: float) -> bool:
    return haversine_km(lat, lng, spot.lat, spot.lng) <= CHECKIN_RADIUS_KM


def _counts(stamps) -> dict[str, int]:
    counts = {"total": 0, "eco": 0}
    for key, _label in COLLECTION_TYPES:
        counts[key] = 0
    for stamp in stamps:
        counts["total"] += 1
        spot_type = stamp.spot.type
        if spot_type in counts:
            counts[spot_type] += 1
        if stamp.eco_action:
            counts["eco"] += 1
    return counts


def earned_badges(stamps) -> list[dict]:
    counts = _counts(stamps)
    return [
        {"id": badge_id, "title": title, "description": description}
        for badge_id, title, description, rule in BADGE_RULES
        if rule(counts)
    ]


def collection_progress(stamps) -> list[dict]:
    counts = _counts(stamps)
    totals = {
        row["type"]: row["n"]
        for row in WaterSpot.objects.values("type").annotate(n=Count("id"))
    }
    rows = []
    for key, label in COLLECTION_TYPES:
        total = totals.get(key, 0)
        if total == 0:
            continue
        rows.append(
            {
                "type": key,
                "label": label,
                "visited": counts.get(key, 0),
                "total": total,
            }
        )
    return rows


def stamp_payload(stamp: Passport) -> dict:
    spot = stamp.spot
    return {
        "id": stamp.id,
        "spot_id": spot.id,
        "name": spot.name,
        "type": spot.type,
        "region": spot.region,
        "verified_at": stamp.verified_at,
        "eco_action": stamp.eco_action,
    }


def passport_payload(user) -> dict:
    stamps = list(
        Passport.objects.filter(user=user).select_related("spot").order_by("-verified_at")
    )
    return {
        "stamps": [stamp_payload(row) for row in stamps],
        "badges": earned_badges(stamps),
        "collection": collection_progress(stamps),
        "visited_count": len(stamps),
    }
