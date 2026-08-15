"""Tag/persona ranking for B1 (no LLM)."""

from __future__ import annotations

from typing import Any, Iterable

from apps.spots.models import WaterSpot

PERSONA_ACTIVITY = {
    "swim": "swim",
    "물놀이": "swim",
    "family": "swim",
    "가족": "swim",
    "surf": "surf",
    "서핑": "surf",
    "active": "surf",
    "액티브": "surf",
    "relax": "relax",
    "healing": "relax",
    "힐링": "relax",
    "물멍": "relax",
    "onsen": "onsen",
    "온천": "onsen",
    "mudflat": "mudflat",
    "갯벌": "mudflat",
    "rafting": "rafting",
    "래프팅": "rafting",
}

MOOD_ACTIVITY = {
    "healing": "relax",
    "힐링": "relax",
    "calm": "relax",
    "release": "surf",
    "해소": "surf",
    "energetic": "surf",
}

PERSONA_TAGS = {
    "swim": ("#물놀이", "#여름휴가", "#에메랄드"),
    "물놀이": ("#물놀이", "#여름휴가", "#에메랄드"),
    "family": ("#가족여행", "#아이와함께", "#여름휴가"),
    "가족": ("#가족여행", "#아이와함께", "#여름휴가"),
    "surf": ("#서핑", "#파도"),
    "서핑": ("#서핑", "#파도"),
    "active": ("#서핑", "#래프팅", "#액티비티", "#파도"),
    "액티브": ("#서핑", "#래프팅", "#액티비티", "#파도"),
    "relax": ("#물멍", "#야경", "#힐링"),
    "healing": ("#물멍", "#힐링", "#온천"),
    "힐링": ("#물멍", "#힐링", "#온천"),
    "물멍": ("#물멍", "#야경"),
    "onsen": ("#온천", "#힐링", "#천연온천"),
    "온천": ("#온천", "#힐링", "#천연온천"),
    "mudflat": ("#갯벌", "#조개잡이"),
    "갯벌": ("#갯벌", "#조개잡이"),
    "rafting": ("#래프팅", "#액티비티"),
    "래프팅": ("#래프팅", "#액티비티"),
}

PERSONA_TYPES = {
    "surf": ("sea",),
    "서핑": ("sea",),
    "onsen": ("hotspring",),
    "온천": ("hotspring",),
    "mudflat": ("tidal_flat",),
    "갯벌": ("tidal_flat",),
    "rafting": ("riverside", "valley"),
    "래프팅": ("riverside", "valley"),
    "relax": ("lake", "valley", "waterfall", "sea"),
    "healing": ("hotspring", "lake", "valley", "waterfall"),
    "힐링": ("hotspring", "lake", "valley", "waterfall"),
    "family": ("sea", "waterpark", "tidal_flat", "pool"),
    "가족": ("sea", "waterpark", "tidal_flat", "pool"),
}


def _norm(token: str) -> str:
    return str(token or "").strip().lower().lstrip("#")


def activity_for_profile(persona: str, mood: str) -> str:
    if persona:
        mapped = PERSONA_ACTIVITY.get(persona.strip()) or PERSONA_ACTIVITY.get(persona.strip().lower())
        if mapped:
            return mapped
    if mood:
        mapped = MOOD_ACTIVITY.get(mood.strip()) or MOOD_ACTIVITY.get(mood.strip().lower())
        if mapped:
            return mapped
    return "swim"


def _wanted_tags(persona: str, mood: str) -> set[str]:
    wanted: set[str] = set()
    for token in (persona, mood):
        tags = PERSONA_TAGS.get(token) or PERSONA_TAGS.get(token.lower())
        if tags:
            wanted.update(_norm(tag) for tag in tags)
    return wanted


def _wanted_types(persona: str, mood: str) -> tuple[str, ...]:
    for token in (persona, mood):
        types = PERSONA_TYPES.get(token) or PERSONA_TYPES.get(token.lower())
        if types:
            return types
    return ()


def _score_for(spot: WaterSpot, activity: str) -> int:
    latest: dict[str, float] = {}
    for row in spot.scores.all():
        latest.setdefault(row.activity, row.score)
    value = latest.get(activity)
    if value is None:
        value = latest.get("swim")
    if value is None:
        return 0
    return int(round(value))


ACTIVITY_LABELS = {
    "swim": "물놀이",
    "surf": "서핑",
    "relax": "물멍",
    "onsen": "온천",
    "mudflat": "갯벌",
    "rafting": "래프팅",
    "family": "가족",
    "healing": "힐링",
    "active": "액티브",
}


def _display_token(token: str, activity: str) -> str:
    if token in ACTIVITY_LABELS:
        return ACTIVITY_LABELS[token]
    if token and any("가" <= char <= "힣" for char in token):
        return token
    return ACTIVITY_LABELS.get(activity, token or activity)


def _reason(*, personalized: bool, activity: str, home: str, persona: str, mood: str) -> str:
    if not personalized:
        return "지금 Water Index가 높은 장소를 모았습니다."
    bits: list[str] = []
    if persona:
        bits.append(f"{_display_token(persona, activity)} 성향")
    elif mood:
        bits.append(f"{_display_token(mood, activity)} 기분")
    if home:
        bits.append(f"{home} 지역")
    bits.append("Water Index")
    return " · ".join(bits) + "를 반영했습니다."


def recommend_spots(
    spots: Iterable[WaterSpot],
    user: Any | None = None,
) -> dict[str, Any]:
    persona = ""
    mood = ""
    home = ""
    personalized = False
    authenticated = bool(user is not None and getattr(user, "is_authenticated", False))
    if authenticated:
        persona = (getattr(user, "persona_type", None) or "").strip()
        mood = (getattr(user, "mood_state", None) or "").strip()
        home = (getattr(user, "home_region", None) or "").strip()
        personalized = bool(persona or mood or home)

    activity = activity_for_profile(persona, mood)
    wanted_tags = _wanted_tags(persona, mood)
    wanted_types = _wanted_types(persona, mood)
    ranked: list[tuple[int, int, int, WaterSpot]] = []
    for spot in spots:
        index = _score_for(spot, activity)
        bonus = 0
        if home and home in (spot.region or ""):
            bonus += 12
        tags = {_norm(tag) for tag in (spot.tags or [])}
        overlap = len(tags & wanted_tags)
        bonus += min(18, overlap * 6)
        if wanted_types and spot.type in wanted_types:
            bonus += 8
        ranked.append((index + bonus, index, spot.id, spot))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return {
        "personalized": personalized,
        "activity": activity,
        "persona_type": persona,
        "mood_state": mood,
        "home_region": home,
        "reason": _reason(
            personalized=personalized,
            activity=activity,
            home=home,
            persona=persona,
            mood=mood,
        ),
        "spots": [item[3] for item in ranked],
    }
