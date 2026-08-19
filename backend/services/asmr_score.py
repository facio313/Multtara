"""Water Sound Library / ASMR index from wave, wind, and rain (C2)."""

from __future__ import annotations

from typing import Any

from apps.content.models import SoundProfile
from apps.spots.models import WaterSpot

SOUND_TYPE = {
    "sea": "wave",
    "tidal_flat": "tidal",
    "valley": "valley",
    "waterfall": "waterfall",
    "lake": "rain",
    "riverside": "valley",
    "hotspring": "rain",
    "pool": "rain",
    "waterpark": "wave",
}

SOUND_LABELS = {
    "wave": "파도",
    "valley": "계곡",
    "waterfall": "폭포",
    "tidal": "갯벌",
    "rain": "비",
}


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def sound_type_for(spot_type: str) -> str:
    return SOUND_TYPE.get(spot_type, "wave")


def calculate_asmr_score(
    wave_height: float | None,
    wind_speed: float | None,
    spot_type: str,
    rainfall: float | None = None,
) -> int:
    """Predict 0-100 sound intensity from marine/weather fields."""
    sound = sound_type_for(spot_type)
    wave = _to_float(wave_height)
    wind = _to_float(wind_speed)
    rain = _to_float(rainfall)
    if sound == "wave":
        score = 40 + wave * 28 + wind * 4
    elif sound == "valley":
        score = 55 + rain * 1.2 + wind * 2
    elif sound == "waterfall":
        score = 70 + rain * 0.8 + wind
    elif sound == "tidal":
        score = 48 + wind * 3 + rain * 0.4
    else:
        score = 50 + rain * 1.5 + wind * 2
    return max(0, min(100, round(score)))


def asmr_payload(spot: WaterSpot, condition: Any = None) -> dict:
    if condition is None:
        cache = getattr(spot, "_prefetched_objects_cache", None)
        if cache is not None and "conditions" in cache:
            condition = next(iter(spot.conditions.all()), None)
        else:
            condition = spot.conditions.order_by("-fetched_at").first()
    sound = sound_type_for(spot.type)
    score = calculate_asmr_score(
        getattr(condition, "wave_height", None),
        getattr(condition, "wind_speed", None),
        spot.type,
        getattr(condition, "rainfall_recent", None),
    )
    stored = SoundProfile.objects.filter(spot=spot).first()
    audio_url = stored.audio_url if stored and stored.audio_url else ""
    mood = "웅장" if score >= 80 else "또렷" if score >= 55 else "잔잔"
    return {
        "sound_type": sound,
        "sound_label": SOUND_LABELS.get(sound, sound),
        "asmr_score": score,
        "audio_url": audio_url,
        "playback": "file" if audio_url else "procedural",
        "mood": mood,
        "blurb": f"오늘 {spot.name} {SOUND_LABELS.get(sound, sound)} 소리 = 백색소음 ASMR {score}점 · {mood}",
    }


def persist_sound_profile(spot: WaterSpot, condition: Any = None) -> SoundProfile:
    payload = asmr_payload(spot, condition)
    row = SoundProfile.objects.filter(spot=spot).first()
    if row is None:
        row = SoundProfile(spot=spot)
    row.sound_type = payload["sound_type"]
    row.asmr_score = payload["asmr_score"]
    row.save()
    return row


def sound_library(limit: int = 40) -> list[dict]:
    spots = list(WaterSpot.objects.all().order_by("id")[:200])
    rows = []
    for spot in spots:
        payload = asmr_payload(spot)
        rows.append(
            {
                "id": spot.id,
                "name": spot.name,
                "region": spot.region,
                "type": spot.type,
                "image_url": spot.image_url,
                **payload,
            }
        )
    rows.sort(key=lambda item: (-(item["asmr_score"] or 0), item["name"]))
    return rows[:limit]
