"""Immutable domain objects for deterministic PongDang recommendations.

The recommendation layer consumes structured, already-normalized evidence.  It
does not ask an LLM to decide whether an activity is safe, open, accessible, or
age appropriate.  Unknown mandatory evidence is deliberately distinct from an
allow decision and therefore fails closed at the recommendation boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


def canonical_name(value: str) -> str:
    """Canonicalize symbolic feature/tag names at the input boundary."""

    canonical = "_".join(value.strip().lower().replace("-", " ").split())
    if not canonical:
        raise ValueError("symbolic name must not be blank")
    return canonical


def _unit_interval(value: float, field_name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be a finite number between 0 and 1")


class GateValue(str, Enum):
    """A structured upstream decision used by hard gates.

    ``UNKNOWN`` is not treated as ``ALLOW``.  Upstream caution policies must be
    resolved deterministically before constructing a candidate; this engine has
    no free-text or LLM safety-decision path.
    """

    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


class ParticipantSkillLevel(str, Enum):
    """Explicit activity skill supplied by the current recommendation request."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True, slots=True)
class PreferenceTarget:
    feature: str
    target: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature", canonical_name(self.feature))
        _unit_interval(self.target, "target")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("preference weight must be a finite positive number")


@dataclass(frozen=True, slots=True)
class PreferenceVector:
    """Continuous user preferences independent of any persona label."""

    targets: tuple[PreferenceTarget, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.targets, key=lambda target: target.feature))
        if not ordered:
            raise ValueError("at least one continuous preference is required")
        names = tuple(target.feature for target in ordered)
        if len(names) != len(set(names)):
            raise ValueError("preference features must be unique")
        object.__setattr__(self, "targets", ordered)

    @property
    def total_weight(self) -> float:
        return sum(target.weight for target in self.targets)


@dataclass(frozen=True, slots=True)
class FeatureValue:
    feature: str
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature", canonical_name(self.feature))
        _unit_interval(self.value, "feature value")


@dataclass(frozen=True, slots=True)
class FeatureVector:
    values: tuple[FeatureValue, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.values, key=lambda item: item.feature))
        names = tuple(item.feature for item in ordered)
        if len(names) != len(set(names)):
            raise ValueError("candidate features must be unique")
        object.__setattr__(self, "values", ordered)

    def get(self, feature: str) -> float | None:
        canonical = canonical_name(feature)
        for item in self.values:
            if item.feature == canonical:
                return item.value
        return None


@dataclass(frozen=True, slots=True)
class AgePolicy:
    """Explicit age evidence.

    ``known=False`` means no age decision can be made.  It is not equivalent to
    an unrestricted venue.
    """

    known: bool
    minimum_age: int = 0
    maximum_age: int | None = None

    def __post_init__(self) -> None:
        if self.minimum_age < 0:
            raise ValueError("minimum_age must be non-negative")
        if self.maximum_age is not None:
            if self.maximum_age < 0:
                raise ValueError("maximum_age must be non-negative")
            if self.maximum_age < self.minimum_age:
                raise ValueError("maximum_age cannot be below minimum_age")


@dataclass(frozen=True, slots=True)
class PartyRequirements:
    ages: tuple[int, ...]
    requires_accessibility: bool = False
    bringing_pet: bool = False
    adult_supervision_confirmed: bool | None = None
    participant_skill_level: ParticipantSkillLevel = (
        ParticipantSkillLevel.UNSPECIFIED
    )

    def __post_init__(self) -> None:
        if not self.ages:
            raise ValueError("at least one party age is required")
        if any(age < 0 or age > 120 for age in self.ages):
            raise ValueError("party ages must be between 0 and 120")
        if self.adult_supervision_confirmed not in {True, False, None}:
            raise TypeError("adult_supervision_confirmed must be true, false, or null")
        try:
            skill_level = (
                self.participant_skill_level
                if isinstance(self.participant_skill_level, ParticipantSkillLevel)
                else ParticipantSkillLevel(str(self.participant_skill_level))
            )
        except ValueError:
            raise ValueError(
                "participant_skill_level must be beginner, intermediate, "
                "advanced, or unspecified"
            ) from None
        object.__setattr__(self, "ages", tuple(sorted(self.ages)))
        object.__setattr__(self, "participant_skill_level", skill_level)


@dataclass(frozen=True, slots=True)
class RecommendationRequest:
    preferences: PreferenceVector
    party: PartyRequirements
    persona_label: str = ""

    def __post_init__(self) -> None:
        # A persona is retained only for display/analytics segmentation.  It is
        # intentionally never canonicalized into a scoring feature.
        object.__setattr__(self, "persona_label", self.persona_label.strip())


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A same-day, half-open availability interval in minutes after midnight.

    An activity ending exactly at ``end_minute`` is feasible.
    """

    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_minute < self.end_minute <= 1_440:
            raise ValueError("time window must satisfy 0 <= start < end <= 1440")


@dataclass(frozen=True, slots=True)
class Candidate:
    """One recommendable place/activity option with structured constraints."""

    spot_id: str
    name: str
    activity: str
    region: str
    features: FeatureVector
    time_windows: tuple[TimeWindow, ...]
    duration_minutes: int
    cost_minor: int | None
    safety: GateValue = GateValue.UNKNOWN
    operation: GateValue = GateValue.UNKNOWN
    accessibility: GateValue = GateValue.UNKNOWN
    pet_policy: GateValue = GateValue.UNKNOWN
    age_policy: AgePolicy = field(default_factory=lambda: AgePolicy(known=False))
    evidence_confidence: float = 0.0
    diversity_tags: frozenset[str] = field(default_factory=frozenset)
    indoor: bool = False
    bad_weather_suitable: bool = False
    fallback_for: str | None = None

    def __post_init__(self) -> None:
        spot_id = self.spot_id.strip()
        name = self.name.strip()
        if not spot_id or not name:
            raise ValueError("candidate spot_id and name are required")
        object.__setattr__(self, "spot_id", spot_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "activity", canonical_name(self.activity))
        object.__setattr__(self, "region", canonical_name(self.region))
        for field_name in ("safety", "operation", "accessibility", "pet_policy"):
            if not isinstance(getattr(self, field_name), GateValue):
                raise TypeError(f"{field_name} must be a GateValue")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.cost_minor is not None and self.cost_minor < 0:
            raise ValueError("cost_minor must be non-negative")
        _unit_interval(self.evidence_confidence, "evidence_confidence")
        ordered_windows = tuple(
            sorted(self.time_windows, key=lambda window: (window.start_minute, window.end_minute))
        )
        object.__setattr__(self, "time_windows", ordered_windows)
        if self.operation is GateValue.ALLOW and not ordered_windows:
            raise ValueError("an operating candidate requires a verified time window")
        if self.operation is GateValue.ALLOW and self.cost_minor is None:
            raise ValueError("an operating candidate requires verified cost evidence")
        object.__setattr__(
            self,
            "diversity_tags",
            frozenset(canonical_name(tag) for tag in self.diversity_tags),
        )
        if self.bad_weather_suitable and not self.indoor:
            raise ValueError("bad_weather_suitable candidates must be indoor")
        if self.fallback_for is not None:
            fallback_for = self.fallback_for.strip()
            if not fallback_for:
                raise ValueError("fallback_for must be a non-blank spot id")
            if fallback_for == spot_id:
                raise ValueError("a candidate cannot be its own fallback")
            object.__setattr__(self, "fallback_for", fallback_for)

    @property
    def diversity_tokens(self) -> frozenset[str]:
        return self.diversity_tags | {
            f"activity:{self.activity}",
            f"region:{self.region}",
        }


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    feature: str
    reason_code: str
    target: float
    candidate_value: float
    similarity: float
    configured_weight: float
    weighted_points: float


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate: Candidate
    hard_gate_passed: bool
    score: float | None
    base_score: float | None
    uncertainty_penalty: float
    effective_confidence: float
    preference_coverage: float
    gate_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    contributions: tuple[ScoreContribution, ...] = field(default_factory=tuple)

    @property
    def eligible(self) -> bool:
        # Defense in depth: even a manually assembled/incorrect assessment
        # cannot launder always-mandatory evidence into a recommendation.
        mandatory_evidence_allows = (
            self.candidate.safety is GateValue.ALLOW
            and self.candidate.operation is GateValue.ALLOW
            and self.candidate.age_policy.known
        )
        return (
            self.hard_gate_passed
            and mandatory_evidence_allows
            and self.score is not None
        )


@dataclass(frozen=True, slots=True)
class RankedRecommendation:
    rank: int
    assessment: CandidateAssessment
    mmr_score: float


@dataclass(frozen=True, slots=True)
class ItineraryRequest:
    start_location_id: str
    end_location_id: str
    start_minute: int
    end_minute: int
    budget_minor: int
    bad_weather: bool = False

    def __post_init__(self) -> None:
        start = self.start_location_id.strip()
        end = self.end_location_id.strip()
        if not start or not end:
            raise ValueError("start_location_id and end_location_id are required")
        if not 0 <= self.start_minute < self.end_minute <= 1_440:
            raise ValueError("itinerary must satisfy 0 <= start < end <= 1440")
        if self.budget_minor < 0:
            raise ValueError("budget_minor must be non-negative")
        object.__setattr__(self, "start_location_id", start)
        object.__setattr__(self, "end_location_id", end)


@dataclass(frozen=True, slots=True)
class ScheduledVisit:
    candidate_id: str
    candidate_name: str
    arrival_minute: int
    start_minute: int
    end_minute: int
    travel_minutes: int
    wait_minutes: int
    cost_minor: int
    reward: float
    is_bad_weather_fallback: bool


@dataclass(frozen=True, slots=True)
class SkippedCandidate:
    candidate_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class ItineraryPlan:
    visits: tuple[ScheduledVisit, ...]
    skipped: tuple[SkippedCandidate, ...]
    total_cost_minor: int
    total_travel_minutes: int
    total_wait_minutes: int
    total_activity_minutes: int
    total_reward: float
    end_arrival_minute: int
    method: str = "deterministic_greedy_orienteering_v1"
    limitations: tuple[str, ...] = (
        "Greedy selection is deterministic but does not prove a globally optimal itinerary.",
        "Travel times and venue windows are assumed to be correct for the requested day.",
        "Bad-weather mode permits only explicitly verified indoor fallback candidates.",
    )


@dataclass(frozen=True, slots=True)
class TravelTime:
    origin_id: str
    destination_id: str
    minutes: int

    def __post_init__(self) -> None:
        origin = self.origin_id.strip()
        destination = self.destination_id.strip()
        if not origin or not destination:
            raise ValueError("travel-time endpoints are required")
        if self.minutes < 0:
            raise ValueError("travel time cannot be negative")
        object.__setattr__(self, "origin_id", origin)
        object.__setattr__(self, "destination_id", destination)
