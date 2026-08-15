"""Public API for PongDang's safety-first Water Index engine."""

from .domain import (
    Activity,
    Decision,
    Environment,
    EvaluationContext,
    IndexResult,
    Metric,
    MetricMode,
    MetricState,
    ObservationSet,
    SafetyStatus,
    SUPPORTED_ACTIVITY_ENVIRONMENTS,
    supports_activity_environment,
)
from .engine import (
    METHODOLOGY_VERSION,
    SAFETY_MAX_AGE_SECONDS,
    evaluation_valid_until,
    evaluate_water_index,
    safety_evidence_valid_until,
)
from .hci import HCIBeachResult, calculate_hci_beach, humidex_from_dew_point

__all__ = [
    "Activity",
    "Decision",
    "Environment",
    "EvaluationContext",
    "IndexResult",
    "HCIBeachResult",
    "METHODOLOGY_VERSION",
    "SAFETY_MAX_AGE_SECONDS",
    "Metric",
    "MetricMode",
    "MetricState",
    "ObservationSet",
    "SafetyStatus",
    "SUPPORTED_ACTIVITY_ENVIRONMENTS",
    "calculate_hci_beach",
    "evaluation_valid_until",
    "evaluate_water_index",
    "safety_evidence_valid_until",
    "supports_activity_environment",
    "humidex_from_dew_point",
]
