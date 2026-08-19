"""Rule-based live travel companion from stored conditions (B4). No LLM."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.spots.models import WaterSpot
from apps.users.stamps import haversine_km
from services.asmr_score import asmr_payload
from services.golden_moment import approximate_sunset, golden_moments
from services.safety_radar import assess_safety
from services.spot_extras import estimate_crowd
from services.tide_timer import summarize_tide

KST = ZoneInfo("Asia/Seoul")
SPEED_KMH = {"car": 55.0, "public": 32.0, "walk": 4.5}
RIP_LABELS = {
    "low": "관심",
    "medium": "주의",
    "high": "위험",
    "주의": "주의",
    "관심": "관심",
    "위험": "위험",
    "경계": "위험",
}


def _latest(spot: WaterSpot, related: str, order: str):
    cache = getattr(spot, "_prefetched_objects_cache", None)
    manager = getattr(spot, related)
    if cache is not None and related in cache:
        return next(iter(manager.all()), None)
    return manager.order_by(order).first()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _eta_minutes(origin_lat: float, origin_lng: float, spot: WaterSpot, transport: str) -> int:
    km = haversine_km(origin_lat, origin_lng, spot.lat, spot.lng)
    speed = SPEED_KMH.get(transport, SPEED_KMH["car"])
    return max(1, round((km / speed) * 60))


def companion_payload(
    spot: WaterSpot,
    *,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
    transport: str = "car",
    now: datetime | None = None,
) -> dict:
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)

    condition = _latest(spot, "conditions", "-fetched_at")
    crowd = _latest(spot, "crowd_levels", "-updated_at")
    safety = assess_safety(spot.type, condition, crowd)
    tide = summarize_tide(getattr(condition, "tide_schedule", None) if condition else {}, current)
    advice: list[dict] = []

    def add(kind: str, text: str, priority: int) -> None:
        advice.append({"kind": kind, "text": text, "priority": priority})

    if safety["level"] == "danger":
        add("safety", f"지금은 위험 신호가 있습니다. {safety['reasons'][0]}", 10)
    elif safety["level"] == "caution":
        add("safety", f"주의가 필요합니다. {safety['reasons'][0]}", 7)

    wave = _to_float(getattr(condition, "wave_height", None))
    if spot.type == "sea" and wave is not None and wave >= 1.2:
        add("wave", "오늘은 파고가 높아 수영보다 산책을 추천합니다.", 8)
    elif spot.type == "sea" and wave is not None and wave < 0.5:
        add("wave", "파도가 잔잔합니다. 물놀이하기 좋은 상태입니다.", 3)

    nxt = tide.get("next") or {}
    if nxt.get("kind") == "low" and nxt.get("minutes", 999) <= 30:
        add("tide", f"{nxt['minutes']}분 후 간조가 시작됩니다.", 8)
    elif nxt.get("kind") == "low" and nxt.get("minutes", 999) <= 180 and spot.type == "tidal_flat":
        add("tide", f"{nxt['minutes']}분 뒤 갯벌 창입니다. 간조 {nxt['time']}.", 6)
    elif nxt.get("kind") == "high" and nxt.get("minutes", 999) <= 40:
        add("tide", f"{nxt['minutes']}분 후 만조입니다.", 5)

    previous = None
    if condition is not None:
        previous = (
            spot.conditions.exclude(pk=condition.pk).order_by("-fetched_at").first()
        )
    if (
        spot.type in {"valley", "riverside", "waterfall"}
        and previous is not None
        and condition.water_level is not None
        and previous.water_level is not None
        and condition.water_level - previous.water_level >= 0.3
    ):
        add("level", "현재 계곡 수위 상승이 감지되었습니다.", 9)

    uv = _to_float(getattr(condition, "uv_index", None))
    if uv is not None and uv >= 8:
        add("uv", f"자외선 {uv:.0f}입니다. 그늘과 선크림을 챙기세요.", 4)

    rip = str(getattr(condition, "rip_current_risk", "") or "")
    if rip in {"high", "위험", "경계"}:
        add("rip", "이안류 위험이 높습니다. 수영은 피하세요.", 9)
    elif rip in {"medium", "주의"}:
        add("rip", "이안류 주의 구간입니다. 안전요원 구역 안에서만 들어가세요.", 6)

    goldens = golden_moments(spot, condition)
    today = current.date().isoformat()
    today_golden = next((row for row in goldens if row["date"] == today and row["type"] == "high_tide_sunset"), None)
    if today_golden:
        add("golden", f"오늘 {today_golden['time']} 만조와 일몰이 겹칩니다. 인생샷 타이밍입니다.", 6)

    sunset = approximate_sunset(spot.lat, spot.lng, current.date())
    sunset_dt = current.replace(hour=sunset.hour, minute=sunset.minute, second=0, microsecond=0)
    eta = None
    if origin_lat is not None and origin_lng is not None:
        eta = _eta_minutes(origin_lat, origin_lng, spot, transport or "car")
        arrive = current.timestamp() + eta * 60
        lead = int((sunset_dt.timestamp() - arrive) / 60)
        if 0 <= lead <= 90:
            add("eta", f"현재 출발하면 일몰 {lead}분 전에 도착 가능합니다.", 5)
        elif lead < 0 and lead >= -40:
            add("eta", "지금 출발하면 일몰을 놓칠 수 있습니다.", 5)

    asmr = asmr_payload(spot, condition)
    if asmr["asmr_score"] >= 80:
        add("sound", asmr["blurb"], 2)

    crowd_row = estimate_crowd(
        spot,
        {
            "predicted_level": getattr(crowd, "predicted_level", None),
            "recommended_time": getattr(crowd, "recommended_time", None),
            "parking_availability": getattr(crowd, "parking_availability", None),
        }
        if crowd
        else None,
    )
    if crowd_row.get("predicted_level") == "high":
        add("crowd", f"지금은 혼잡합니다. {crowd_row.get('recommended_time') or '이른 시간'} 방문을 권합니다.", 4)

    if not advice:
        add("ok", "지금은 특이 경보가 없습니다. 컨디션을 보고 즐기세요.", 1)

    advice.sort(key=lambda item: -item["priority"])
    return {
        "spot_id": spot.id,
        "name": spot.name,
        "advice": advice,
        "headline": advice[0]["text"],
        "safety": safety,
        "tide": tide,
        "eta_minutes": eta,
        "sunset": sunset.strftime("%H:%M"),
        "rip_label": RIP_LABELS.get(rip, rip or None),
        "generated_at": current.isoformat(),
    }
