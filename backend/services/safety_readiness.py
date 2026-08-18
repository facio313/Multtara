"""Read-only audit of current, evidence-backed Water Index availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from django.db.models import Q

from apps.conditions.models import ConditionScore
from apps.conditions.serializers import ConditionScoreSerializer
from services.ingestion.fusion import activity_supported_for_spot
from services.water_index import Activity


@dataclass(frozen=True, slots=True)
class SafetyReadinessEntry:
    spot_id: int
    spot_name: str
    activity: str
    participant_profile: str
    safety_status: str
    decision: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SafetyReadinessReport:
    checked_at: datetime
    entries: tuple[SafetyReadinessEntry, ...]

    @property
    def counts(self) -> dict[str, int]:
        counts = {status: 0 for status in ("clear", "caution", "stop", "unknown")}
        for entry in self.entries:
            counts[entry.safety_status] = counts.get(entry.safety_status, 0) + 1
        return counts

    @property
    def current_clear_count(self) -> int:
        return self.counts["clear"]


def audit_safety_readiness(
    *,
    at: datetime,
    spots: Iterable[Any],
    profiles: tuple[str, ...] = ("general", "family"),
) -> SafetyReadinessReport:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("safety readiness time must be timezone-aware")
    if not profiles or any(profile not in {"general", "family"} for profile in profiles):
        raise ValueError("profiles must contain general and/or family")

    normalized_spots = tuple(spots)
    if len(normalized_spots) > 500:
        raise ValueError("safety readiness audit is limited to 500 spots")

    entries: list[SafetyReadinessEntry] = []
    for spot in normalized_spots:
        for activity in Activity:
            if not activity_supported_for_spot(spot, activity):
                continue
            for profile in profiles:
                if profile == "family" and activity is not Activity.SWIM:
                    continue
                score = _latest_score(
                    spot=spot,
                    activity=activity.value,
                    profile=profile,
                    at=at,
                )
                if score is None:
                    entries.append(
                        SafetyReadinessEntry(
                            spot_id=spot.pk,
                            spot_name=spot.name,
                            activity=activity.value,
                            participant_profile=profile,
                            safety_status="unknown",
                            decision="unknown",
                            reason_codes=("EVALUATION_MISSING",),
                        )
                    )
                    continue

                data = ConditionScoreSerializer(
                    score,
                    context={"effective_as_of": at},
                ).data
                reason_codes = tuple(
                    dict.fromkeys(
                        gate.get("reason_code")
                        for gate in data.get("gates", ())
                        if isinstance(gate, dict) and gate.get("reason_code")
                    )
                )
                entries.append(
                    SafetyReadinessEntry(
                        spot_id=spot.pk,
                        spot_name=spot.name,
                        activity=activity.value,
                        participant_profile=profile,
                        safety_status=str(data["safety_status"]),
                        decision=str(data["decision"]),
                        reason_codes=reason_codes,
                    )
                )
    return SafetyReadinessReport(checked_at=at, entries=tuple(entries))


def _latest_score(*, spot: Any, activity: str, profile: str, at: datetime):
    return (
        ConditionScore.objects.select_related("spot", "snapshot", "snapshot__spot")
        .prefetch_related("snapshot__metrics")
        .filter(
            spot=spot,
            activity=activity,
            participant_profile=profile,
            participant_skill_level="unspecified",
            evaluated_at__lte=at,
        )
        .filter(
            Q(snapshot__isnull=True)
            | Q(snapshot__valid_from__isnull=True)
            | Q(snapshot__valid_from__lte=at)
        )
        .filter(Q(snapshot__isnull=True) | Q(snapshot__spot=spot))
        .order_by("-evaluated_at", "-id")
        .first()
    )
