"""Rule-based day plan from start region, party, and Water Index (no LLM)."""

from __future__ import annotations

from typing import Any

from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary
from services.recommend import recommend_spots

REGION_NEIGHBORS = {
    "서울": ("서울", "경기", "인천"),
    "경기": ("경기", "서울", "인천", "강원"),
    "인천": ("인천", "경기", "서울"),
    "강원": ("강원", "경기", "경북"),
    "부산": ("부산", "경남", "울산"),
    "경남": ("경남", "부산", "울산"),
    "울산": ("울산", "부산", "경남"),
    "제주": ("제주",),
    "충북": ("충북", "충남", "경기"),
    "충남": ("충남", "대전", "충북"),
    "대전": ("대전", "충남", "충북"),
    "전북": ("전북", "전남", "충남"),
    "전남": ("전남", "광주", "전북"),
    "광주": ("광주", "전남"),
    "경북": ("경북", "대구", "강원"),
    "대구": ("대구", "경북"),
}


def _persona_for(party_size: int, activity: str) -> str:
    if party_size >= 3:
        return "family"
    return activity or "swim"


def build_itinerary(
    *,
    start_point: str,
    transport: str = "car",
    is_day_trip: bool = True,
    party_size: int = 1,
    budget: int | None = None,
    activity: str = "",
    user=None,
    save: bool = False,
) -> dict[str, Any]:
    persona = _persona_for(party_size, activity)
    payload = recommend_spots(WaterSpot.objects.prefetch_related("scores", "conditions"), user)
    spots = payload["spots"]
    region = (start_point or "").strip()
    neighbors = REGION_NEIGHBORS.get(region, ())
    if neighbors:
        local = [spot for spot in spots if spot.region in neighbors]
        spots = local or spots
    if persona == "family":
        family = [spot for spot in spots if spot.type in {"sea", "waterpark", "tidal_flat", "pool"}]
        spots = family or spots
    count = 2 if is_day_trip else 3
    chosen = spots[:count]
    times = ("09:30", "13:00", "16:30")
    legs = []
    for index, spot in enumerate(chosen):
        legs.append(
            {
                "time": times[index],
                "spot_id": spot.id,
                "name": spot.name,
                "type": spot.type,
                "region": spot.region,
            }
        )
    note = "당일치기" if is_day_trip else "1박"
    if party_size >= 3:
        note += " · 가족 동선"
    if budget:
        note += f" · 예산 {budget:,}원"
    schedule = {"legs": legs, "note": note, "transport": transport, "start_point": region}
    saved_id = None
    if save and user is not None and getattr(user, "is_authenticated", False):
        row = Itinerary.objects.create(
            user=user,
            start_point=region,
            transport=transport,
            is_day_trip=is_day_trip,
            party_size=party_size,
            budget=budget,
            schedule=schedule,
        )
        saved_id = row.id
    return {
        "id": saved_id,
        "activity": payload["activity"] if not activity else activity,
        "persona_type": persona,
        **schedule,
    }
