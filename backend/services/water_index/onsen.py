"""Pure, request-scoped facility-fit overlays for hot-spring ranking.

The three values in this module depend on the current user's explicit request
or on short-lived context. They are deliberately not normalized provider
observations and must never be persisted as global condition evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from types import MappingProxyType
from typing import Mapping

from .domain import Metric, MetricMode, MetricState, ObservationSet


ONSEN_SESSION_OVERLAY_VERSION = "onsen-session-overlay-v1"
_SESSION_FACTOR_NAMES = frozenset(
    {"amenity_fit", "crowd_fit", "preferred_temperature_fit"}
)


def _canonical_name(value: str) -> str:
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    if not normalized:
        raise ValueError("amenity names cannot be blank")
    return normalized


def _unit_interval(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number from 0 to 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be a finite number from 0 to 1")
    return normalized


@dataclass(frozen=True, slots=True)
class OnsenSessionPreferences:
    """Only non-``None`` fields were explicitly supplied by this request."""

    required_amenities: tuple[str, ...] | None = None
    crowd_target: float | None = None
    preferred_temperature_c: float | None = None
    temperature_tolerance_c: float = 5.0

    def __post_init__(self) -> None:
        if self.required_amenities is not None:
            names = tuple(_canonical_name(item) for item in self.required_amenities)
            if len(names) != len(set(names)):
                raise ValueError("required amenities must be unique")
            object.__setattr__(self, "required_amenities", names)
        if self.crowd_target is not None:
            object.__setattr__(
                self,
                "crowd_target",
                _unit_interval(self.crowd_target, "crowd_target"),
            )
        if self.preferred_temperature_c is not None:
            if (
                isinstance(self.preferred_temperature_c, bool)
                or not isinstance(self.preferred_temperature_c, (int, float))
                or not math.isfinite(float(self.preferred_temperature_c))
            ):
                raise ValueError("preferred_temperature_c must be finite")
            object.__setattr__(
                self,
                "preferred_temperature_c",
                float(self.preferred_temperature_c),
            )
        if (
            isinstance(self.temperature_tolerance_c, bool)
            or not isinstance(self.temperature_tolerance_c, (int, float))
            or not math.isfinite(float(self.temperature_tolerance_c))
            or float(self.temperature_tolerance_c) <= 0
        ):
            raise ValueError("temperature_tolerance_c must be finite and positive")


@dataclass(frozen=True, slots=True)
class OnsenSessionEvidence:
    """Request-time catalog/live values; ``None`` means not evidenced."""

    amenities: frozenset[str] | None = None
    crowd_level: float | None = None
    water_temperature_c: float | None = None

    def __post_init__(self) -> None:
        if self.amenities is not None:
            object.__setattr__(
                self,
                "amenities",
                frozenset(_canonical_name(item) for item in self.amenities),
            )
        if self.crowd_level is not None:
            object.__setattr__(
                self,
                "crowd_level",
                _unit_interval(self.crowd_level, "crowd_level"),
            )
        if self.water_temperature_c is not None:
            if (
                isinstance(self.water_temperature_c, bool)
                or not isinstance(self.water_temperature_c, (int, float))
                or not math.isfinite(float(self.water_temperature_c))
            ):
                raise ValueError("water_temperature_c must be finite")
            object.__setattr__(
                self,
                "water_temperature_c",
                float(self.water_temperature_c),
            )


@dataclass(frozen=True, slots=True)
class OnsenSessionOverlay:
    """Non-persistable factor values for one recommendation evaluation."""

    metrics: Mapping[str, float]
    methodology_version: str = ONSEN_SESSION_OVERLAY_VERSION
    source: str = "SESSION_CONTEXT"
    persistable: bool = False

    def __post_init__(self) -> None:
        normalized = dict(self.metrics)
        if not set(normalized).issubset(_SESSION_FACTOR_NAMES):
            raise ValueError("onsen session overlay contains an unsupported factor")
        normalized = {
            name: _unit_interval(value, name)
            for name, value in normalized.items()
        }
        if self.source != "SESSION_CONTEXT" or self.persistable:
            raise ValueError("onsen session overlays must remain non-persistable context")
        object.__setattr__(self, "metrics", MappingProxyType(normalized))


def build_onsen_session_overlay(
    *,
    preferences: OnsenSessionPreferences,
    evidence: OnsenSessionEvidence,
) -> OnsenSessionOverlay:
    """Build only factors whose matching preference was explicitly supplied.

    This is a deterministic ranking overlay, not a medical benefit claim and
    not a facility-safety clearance. Missing request fields or missing matching
    evidence produce no metric rather than a neutral/default score.
    """

    metrics: dict[str, float] = {}
    required = preferences.required_amenities
    if required and evidence.amenities is not None:
        matched = sum(name in evidence.amenities for name in required)
        metrics["amenity_fit"] = matched / len(required)
    if preferences.crowd_target is not None and evidence.crowd_level is not None:
        metrics["crowd_fit"] = 1.0 - abs(
            preferences.crowd_target - evidence.crowd_level
        )
    if (
        preferences.preferred_temperature_c is not None
        and evidence.water_temperature_c is not None
    ):
        distance = abs(
            preferences.preferred_temperature_c - evidence.water_temperature_c
        )
        metrics["preferred_temperature_fit"] = max(
            0.0,
            1.0 - distance / float(preferences.temperature_tolerance_c),
        )
    return OnsenSessionOverlay(metrics=metrics)


def apply_onsen_session_overlay(
    *,
    observations: ObservationSet,
    overlay: OnsenSessionOverlay,
    at: datetime,
) -> ObservationSet:
    """Overlay request factors onto an in-memory observation set only.

    Any globally sourced values with these session-only names are removed,
    including when the current request omitted the corresponding preference.
    The returned metrics expire at this exact evaluation time and have no
    persistence adapter contract.
    """

    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    retained = tuple(
        metric
        for metric in observations.metrics.values()
        if metric.name not in _SESSION_FACTOR_NAMES
    )
    contextual = tuple(
        Metric(
            name=name,
            value=value,
            unit="proportion",
            source="SESSION_CONTEXT",
            source_url="",
            station_id="",
            spatial_scope="session:recommendation-request",
            observed_at=at,
            fetched_at=at,
            valid_from=at,
            valid_until=at,
            mode=MetricMode.ESTIMATED,
            confidence=1.0,
            state=MetricState.VALID,
        )
        for name, value in overlay.metrics.items()
    )
    return ObservationSet.from_metrics(*retained, *contextual)
