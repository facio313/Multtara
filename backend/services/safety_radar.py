"""Safety radar from stored WaterCondition fields. No extra public API."""

from __future__ import annotations

from typing import Any

LEVEL_ORDER = {"safe": 0, "caution": 1, "danger": 2}
LEVEL_LABELS = {"safe": "양호", "caution": "주의", "danger": "위험"}


def _value(source: Any, name: str):
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def assess_safety(spot_type: str, condition: Any = None, crowd: Any = None) -> dict:
    level = "safe"
    reasons: list[str] = []

    def bump(next_level: str, reason: str) -> None:
        nonlocal level
        if LEVEL_ORDER[next_level] > LEVEL_ORDER[level]:
            level = next_level
        reasons.append(reason)

    rainfall = _to_float(_value(condition, "rainfall_recent"))
    water_level = _to_float(_value(condition, "water_level"))
    wave = _to_float(_value(condition, "wave_height"))
    rip = str(_value(condition, "rip_current_risk") or "").lower()
    alert = str(_value(condition, "weather_alert") or "").strip()
    crowd_level = str(_value(crowd, "predicted_level") or "").lower()

    if alert:
        if any(token in alert for token in ("경보", "호우", "태풍", "특보", "위험")):
            bump("danger", alert)
        else:
            bump("caution", alert)

    if spot_type in {"valley", "riverside", "waterfall"}:
        if rainfall is not None and rainfall >= 30:
            bump("danger", f"최근 강수 {rainfall:.0f}mm")
        elif rainfall is not None and rainfall >= 10:
            bump("caution", f"최근 강수 {rainfall:.0f}mm")
        if water_level is not None and water_level >= 1.5:
            bump("danger", f"수위 {water_level}m")
        elif water_level is not None and water_level >= 0.8:
            bump("caution", f"수위 {water_level}m")
        if not reasons:
            reasons.append("호우·수위 특이사항 없음")

    elif spot_type == "sea":
        if rip in {"high", "danger", "위험", "경계"}:
            bump("danger", "이안류 위험 높음")
        elif rip in {"medium", "caution", "주의"}:
            bump("caution", "이안류 주의")
        if wave is not None and wave >= 2:
            bump("danger", f"파고 {wave}m")
        elif wave is not None and wave >= 1.2:
            bump("caution", f"파고 {wave}m")
        if not reasons:
            reasons.append("이안류·파고 특이사항 없음")

    elif spot_type == "tidal_flat":
        if not reasons:
            reasons.append("물때를 확인하고 체험하세요")

    elif spot_type == "hotspring":
        if crowd_level in {"high", "혼잡", "very_high"}:
            bump("caution", "혼잡")
        if not reasons:
            reasons.append("혼잡·대기 정보")

    else:
        if rainfall is not None and rainfall >= 30:
            bump("danger", f"최근 강수 {rainfall:.0f}mm")
        elif rainfall is not None and rainfall >= 10:
            bump("caution", f"최근 강수 {rainfall:.0f}mm")
        if not reasons:
            reasons.append("특이 경보 없음")

    return {
        "level": level,
        "label": LEVEL_LABELS[level],
        "reasons": reasons,
        "kind": spot_type,
    }


def twin_facts(spot_type: str, condition: Any, crowd: Any, tide: dict | None) -> list[dict]:
    def fact(label: str, value: Any) -> dict | None:
        if value is None or value == "" or value == []:
            return None
        return {"label": label, "value": value}

    rows: list[dict | None] = []
    water_temp = _value(condition, "water_temp")
    air_temp = _value(condition, "air_temp")
    wind = _value(condition, "wind_speed")
    wave = _value(condition, "wave_height")
    quality = _value(condition, "water_quality_grade")
    rip = _value(condition, "rip_current_risk")
    rain = _value(condition, "rainfall_recent")
    level = _value(condition, "water_level")
    nxt = (tide or {}).get("next") or {}

    if spot_type == "sea":
        rows = [
            fact("수온", None if water_temp is None else f"{water_temp}°C"),
            fact("파고", None if wave is None else f"{wave}m"),
            fact("풍속", None if wind is None else f"{wind}m/s"),
            fact("이안류", rip),
            fact("수질", quality),
        ]
    elif spot_type in {"valley", "riverside", "waterfall"}:
        rows = [
            fact("수온", None if water_temp is None else f"{water_temp}°C"),
            fact("수위", None if level is None else f"{level}m"),
            fact("강수", None if rain is None else f"{rain}mm"),
            fact("수질", quality),
        ]
    elif spot_type == "hotspring":
        rec = _value(crowd, "recommended_time")
        crowd_level = _value(crowd, "predicted_level")
        rows = [
            fact("수온", None if water_temp is None else f"{water_temp}°C"),
            fact("혼잡", crowd_level),
            fact("추천", rec),
        ]
    elif spot_type == "tidal_flat":
        low = ", ".join((tide or {}).get("low_tide") or []) or None
        high = ", ".join((tide or {}).get("high_tide") or []) or None
        nxt_text = None
        if nxt:
            when = "내일 " if nxt.get("is_tomorrow") else ""
            nxt_text = f"{when}{nxt.get('label')} {nxt.get('time')}"
        rows = [
            fact("간조", low),
            fact("만조", high),
            fact("다음 물때", nxt_text),
        ]
    else:
        rows = [
            fact("수온", None if water_temp is None else f"{water_temp}°C"),
            fact("기온", None if air_temp is None else f"{air_temp}°C"),
            fact("강수", None if rain is None else f"{rain}mm"),
        ]
    return [row for row in rows if row]
