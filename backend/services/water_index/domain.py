"""Domain types for the versioned PongDang Water Index.

The index deliberately separates suitability from safety. A pleasant weather
score is never allowed to override an official closure, warning, or an
insufficient safety-data state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias


MetricValue: TypeAlias = float | int | str | bool

SURF_PARTICIPANT_SKILL_LEVELS = frozenset(
    {"beginner", "intermediate", "advanced", "unspecified"}
)


class Activity(str, Enum):
    SWIM = "swim"
    SURF = "surf"
    RELAX = "relax"
    MUDFLAT = "mudflat"
    ONSEN = "onsen"
    RAFTING = "rafting"


class Environment(str, Enum):
    MARINE_BEACH = "marine_beach"
    INLAND_WATER = "inland_water"
    WATERSIDE = "waterside"
    TIDAL_FLAT = "tidal_flat"
    LICENSED_FACILITY = "licensed_facility"
    RIVER = "river"


class MetricMode(str, Enum):
    OBSERVED = "observed"
    FORECAST = "forecast"
    ESTIMATED = "estimated"
    USER_REPORTED = "user_reported"


class MetricState(str, Enum):
    VALID = "valid"
    CONFLICT = "conflict"
    INVALID = "invalid"


class Decision(str, Enum):
    RECOMMENDED = "recommended"
    CONSIDER = "consider"
    CAUTION = "caution"
    NOT_RECOMMENDED = "not_recommended"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class SafetyStatus(str, Enum):
    CLEAR = "clear"
    CAUTION = "caution"
    STOP = "stop"
    UNKNOWN = "unknown"


SUPPORTED_ACTIVITY_ENVIRONMENTS = MappingProxyType(
    {
        Activity.SWIM: frozenset(
            {Environment.MARINE_BEACH, Environment.INLAND_WATER}
        ),
        Activity.SURF: frozenset({Environment.MARINE_BEACH}),
        Activity.RELAX: frozenset({Environment.MARINE_BEACH}),
        Activity.MUDFLAT: frozenset({Environment.TIDAL_FLAT}),
        Activity.ONSEN: frozenset({Environment.LICENSED_FACILITY}),
        Activity.RAFTING: frozenset({Environment.RIVER, Environment.INLAND_WATER}),
    }
)


def supports_activity_environment(
    activity: Activity,
    environment: Environment,
) -> bool:
    return environment in SUPPORTED_ACTIVITY_ENVIRONMENTS[activity]


class RuleSeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    BLOCK = "block"
    UNKNOWN = "unknown"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Metric:
    """One normalized metric with enough provenance to audit a decision."""

    name: str
    value: MetricValue
    unit: str
    source: str
    spatial_scope: str
    observed_at: datetime
    fetched_at: datetime
    valid_until: datetime | None
    source_url: str = ""
    station_id: str = ""
    mode: MetricMode = MetricMode.OBSERVED
    confidence: float = 1.0
    state: MetricState = MetricState.VALID
    valid_from: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name is required")
        if not self.source.strip():
            raise ValueError("metric source is required")
        if not self.spatial_scope.strip():
            raise ValueError("metric spatial_scope is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("metric confidence must be between 0 and 1")
        if (
            isinstance(self.value, (int, float))
            and not isinstance(self.value, bool)
            and not math.isfinite(float(self.value))
        ):
            raise ValueError("numeric metric values must be finite")
        _require_aware(self.observed_at, "observed_at")
        _require_aware(self.fetched_at, "fetched_at")
        if self.observed_at > self.fetched_at:
            raise ValueError("observed_at cannot be later than fetched_at")
        if self.valid_from is not None:
            _require_aware(self.valid_from, "valid_from")
        if self.valid_until is not None:
            _require_aware(self.valid_until, "valid_until")
            if self.valid_from is not None and self.valid_until < self.valid_from:
                raise ValueError("valid_until cannot precede valid_from")
        if self.mode is MetricMode.FORECAST and (
            self.valid_from is None or self.valid_until is None
        ):
            raise ValueError("forecast metrics require valid_from and valid_until")

    def is_current(self, at: datetime, *, max_age_seconds: int | None) -> bool:
        """Return whether the metric is usable at ``at``.

        Safety-critical metrics with neither an explicit validity interval nor
        a policy max-age are not silently treated as current.
        """

        _require_aware(at, "at")
        if self.state is not MetricState.VALID:
            return False
        if self.mode is not MetricMode.FORECAST and at < self.observed_at:
            return False
        if self.valid_from is not None and at < self.valid_from:
            return False
        expiries: list[datetime] = []
        if self.valid_until is not None:
            expiries.append(self.valid_until)
        # Observation freshness limits are measured from an observation time.
        # A typed forecast instead has an explicit provider validity window;
        # applying an observation max-age to its issue time would make a
        # legitimate future STOP/UNKNOWN signal disappear before it starts.
        if max_age_seconds is not None and self.mode is not MetricMode.FORECAST:
            expiries.append(
                self.observed_at + timedelta(seconds=max_age_seconds)
            )
        if not expiries:
            return False
        return at <= min(expiries)


@dataclass(frozen=True, slots=True)
class ObservationSet:
    """Immutable, canonical snapshot consumed by one evaluation."""

    metrics: Mapping[str, Metric]

    def __post_init__(self) -> None:
        copied = dict(self.metrics)
        for key, metric in copied.items():
            if key != metric.name:
                raise ValueError(f"metric key {key!r} does not match {metric.name!r}")
        object.__setattr__(self, "metrics", MappingProxyType(copied))

    @classmethod
    def from_metrics(cls, *metrics: Metric) -> "ObservationSet":
        by_name: dict[str, Metric] = {}
        for metric in metrics:
            if metric.name in by_name:
                raise ValueError(f"duplicate canonical metric: {metric.name}")
            by_name[metric.name] = metric
        return cls(by_name)

    def get(self, name: str) -> Metric | None:
        return self.metrics.get(name)


_DEFAULT_ENVIRONMENT = {
    Activity.SWIM: Environment.MARINE_BEACH,
    Activity.SURF: Environment.MARINE_BEACH,
    Activity.RELAX: Environment.MARINE_BEACH,
    Activity.MUDFLAT: Environment.TIDAL_FLAT,
    Activity.ONSEN: Environment.LICENSED_FACILITY,
    Activity.RAFTING: Environment.RIVER,
}


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    activity: Activity
    at: datetime
    environment: Environment | None = None
    participant_profile: str = "general"
    participant_skill_level: str = "unspecified"

    def __post_init__(self) -> None:
        _require_aware(self.at, "at")
        raw_skill_level = getattr(
            self.participant_skill_level,
            "value",
            self.participant_skill_level,
        )
        skill_level = str(raw_skill_level).strip().lower()
        if skill_level not in SURF_PARTICIPANT_SKILL_LEVELS:
            raise ValueError(
                "participant_skill_level must be beginner, intermediate, "
                "advanced, or unspecified"
            )
        object.__setattr__(self, "participant_skill_level", skill_level)
        if self.environment is None:
            object.__setattr__(self, "environment", _DEFAULT_ENVIRONMENT[self.activity])
        if not supports_activity_environment(self.activity, self.environment):
            raise ValueError(
                f"unsupported activity/environment combination: "
                f"{self.activity.value}/{self.environment.value}"
            )


@dataclass(frozen=True, slots=True)
class RuleResult:
    rule_id: str
    severity: RuleSeverity
    metric_name: str
    reason_code: str
    source: str = ""
    source_url: str = ""
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Contribution:
    metric_name: str
    normalized_score: float
    configured_weight: float
    effective_weight: float
    weighted_points: float
    evidence_basis: str
    source: str
    source_url: str
    observed_at: datetime
    mode: MetricMode


@dataclass(frozen=True, slots=True)
class IndexResult:
    methodology_version: str
    activity: Activity
    environment: Environment
    safety_status: SafetyStatus
    decision: Decision
    score: int | None
    score_range: tuple[float, float] | None
    confidence: float
    coverage: float
    evaluated_at: datetime
    gates: tuple[RuleResult, ...] = field(default_factory=tuple)
    contributions: tuple[Contribution, ...] = field(default_factory=tuple)
    missing_metrics: tuple[str, ...] = field(default_factory=tuple)
    stale_or_conflicting_metrics: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def eligible_for_recommendation(self) -> bool:
        return self.safety_status is SafetyStatus.CLEAR and self.decision in {
            Decision.RECOMMENDED,
            Decision.CONSIDER,
        }
