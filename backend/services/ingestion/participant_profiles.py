"""Canonical participant profiles shared by evaluation persistence boundaries."""

from __future__ import annotations


GENERAL_PROFILE = "general"
FAMILY_PROFILE = "family"

_PROFILE_ALIASES = {
    GENERAL_PROFILE: GENERAL_PROFILE,
    FAMILY_PROFILE: FAMILY_PROFILE,
    "beginner": FAMILY_PROFILE,
    "family_swim": FAMILY_PROFILE,
}


def canonical_participant_profile(value: str) -> str:
    """Normalize supported profile aliases without inventing new policies."""

    canonical = "_".join(value.strip().lower().replace("-", " ").split())
    try:
        return _PROFILE_ALIASES[canonical]
    except KeyError:
        raise ValueError("participant_profile must be general or family") from None
