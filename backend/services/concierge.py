"""Natural-language spot ranking without an LLM."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Prefetch

from apps.conditions.models import ConditionScore, WaterCondition
from apps.spots.models import WaterSpot
from services.recommend import recommend_spots

KEYWORD_PERSONA = (
    (("아이", "가족", "어린이", "키즈"), "family"),
    (("온천", "탕", "노천"), "onsen"),
    (("서핑", "파도", "보드"), "surf"),
    (("갯벌", "조개", "개펄"), "mudflat"),
    (("래프팅", "카약", "급류"), "rafting"),
    (("힐링", "물멍", "조용", "고요"), "relax"),
    (("계곡", "폭포"), "relax"),
)


@dataclass
class FakeUser:
    is_authenticated = True
    persona_type: str = ""
    mood_state: str = ""
    home_region: str = ""


def parse_query(query: str) -> dict:
    text = (query or "").strip()
    persona = ""
    mood = ""
    home = ""
    avoid_rain = any(token in text for token in ("비", "우천", "장마"))
    pet = "반려" in text or "애견" in text
    for tokens, value in KEYWORD_PERSONA:
        if any(token in text for token in tokens):
            persona = value
            break
    for region in ("제주", "부산", "강원", "경기", "서울", "인천", "충남", "충북", "전남", "전북", "경남", "경북"):
        if region in text:
            home = region
            break
    if "해소" in text or "스트레스" in text:
        mood = "release"
    return {
        "persona_type": persona,
        "mood_state": mood,
        "home_region": home,
        "avoid_rain": avoid_rain,
        "pet": pet,
        "query": text,
    }


def concierge_spots(query: str, user=None) -> dict:
    parsed = parse_query(query)
    queryset = WaterSpot.objects.prefetch_related(
        Prefetch("scores", queryset=ConditionScore.objects.order_by("-computed_at")),
        Prefetch("conditions", queryset=WaterCondition.objects.order_by("-fetched_at")),
    )
    if parsed["pet"]:
        queryset = queryset.filter(pet_allowed=True)
    persona = parsed["persona_type"]
    mood = parsed["mood_state"]
    home = parsed["home_region"]
    if user is not None and getattr(user, "is_authenticated", False):
        persona = persona or (user.persona_type or "")
        mood = mood or (user.mood_state or "")
        home = home or (user.home_region or "")
    fake = FakeUser(persona_type=persona, mood_state=mood, home_region=home)
    payload = recommend_spots(queryset, fake)
    spots = payload["spots"]
    if parsed["avoid_rain"]:
        dry = []
        for spot in spots:
            condition = next(iter(spot.conditions.all()), None)
            rain = getattr(condition, "rainfall_recent", None) or 0
            if rain < 10 or spot.type == "hotspring":
                dry.append(spot)
        spots = dry or spots
    reason = "질문을 규칙으로 해석해 순위를 매겼습니다."
    if parsed["query"]:
        reason = f"“{parsed['query']}” → {payload['reason']}"
    return {
        **payload,
        "spots": spots,
        "parsed": parsed,
        "reason": reason,
    }
