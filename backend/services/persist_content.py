"""Persist derived content tables after a condition refresh."""

from __future__ import annotations

from apps.spots.models import WaterSpot
from services.asmr_score import persist_sound_profile
from services.golden_moment import persist_golden_moments
from services.spot_analytics import persist_analytics
from services.spot_extras import seed_spot_extras


def persist_spot_content(spot: WaterSpot) -> None:
    seed_spot_extras(spot)
    persist_sound_profile(spot)
    persist_golden_moments(spot)
    persist_analytics(spot)
