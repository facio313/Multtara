"""Safety-first Water Index evaluation engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .domain import (
    Activity,
    Contribution,
    Decision,
    Environment,
    EvaluationContext,
    IndexResult,
    Metric,
    ObservationSet,
    RuleResult,
    RuleSeverity,
    SafetyStatus,
)
from .profiles import PROFILES, ScoreProfile
from .surf_skill import (
    SURF_GRADE_DETAIL_MISSING,
    SURF_OFFICIAL_GRADE_MISSING,
    SURF_SKILL_LEVEL_REQUIRED,
    SurfSkillEvidenceAssessment,
    assess_surf_skill_evidence,
)


METHODOLOGY_VERSION = "water-index-v1.0.0"
MINIMUM_SAFETY_INPUT_CONFIDENCE = 0.80


@dataclass(frozen=True, slots=True)
class Requirement:
    rule_id: str
    any_of: tuple[str, ...]
    reason_code: str


SAFETY_MAX_AGE_SECONDS: dict[str, int | None] = {
    "official_stop_signal": 900,
    "access_status": 900,
    "official_entry_status": 900,
    "patrol_status": 900,
    "designated_swim_zone_status": 900,
    "adult_supervision_status": 900,
    "facility_status": 1_800,
    "operator_status": 900,
    "weather_alert_level": 600,
    "lightning_clearance_minutes": 300,
    "rip_current_risk": 1_200,
    "water_quality_status": None,
    "river_risk_level": 900,
    "tide_window_open": None,
    "marine_hazard_status": 600,
    "fog_status": 600,
    "designated_route_status": 21_600,
    "facility_hygiene_status": None,
    "hot_tub_temperature_c": 1_800,
    "safety_equipment_status": 900,
    "upstream_rain_risk": 900,
    "water_temperature_c": 3_600,
}

_ALWAYS_EVALUATED_SIGNALS = frozenset(SAFETY_MAX_AGE_SECONDS)


def safety_evidence_valid_until(metric: Metric) -> datetime | None:
    """Return the earliest provider or policy expiry for a safety metric.

    An observed value's explicit provider interval never extends the activity
    policy's maximum age. A typed forecast is governed by its required provider
    validity window: measuring observation freshness from the forecast issue
    time would expire future evidence before its validity starts. ``None``
    means the metric has no usable expiry and must not be treated as current
    safety evidence.
    """

    if metric.name not in SAFETY_MAX_AGE_SECONDS:
        return metric.valid_until
    expiries: list[datetime] = []
    if metric.valid_until is not None:
        expiries.append(metric.valid_until)
    max_age_seconds = SAFETY_MAX_AGE_SECONDS[metric.name]
    if max_age_seconds is not None and metric.mode.value != "forecast":
        expiries.append(metric.observed_at + timedelta(seconds=max_age_seconds))
    return min(expiries) if expiries else None


def evaluation_valid_until(
    observations: ObservationSet,
    context: EvaluationContext,
) -> datetime:
    """Return the fail-closed expiry of an activity's safety evaluation.

    Every required alternative group must contain current evidence. Missing,
    conflicting, low-confidence, or non-expiring evidence makes the persisted
    evaluation valid only at its evaluation instant. Present optional safety
    signals also shorten the window so a clear signal cannot outlive its own
    provider/policy expiry.
    """

    expiries: list[datetime] = []
    required_names: set[str] = set()
    for requirement in _requirements(context):
        selected: Metric | None = None
        for name in requirement.any_of:
            required_names.add(name)
            metric, _ = _current_metric(
                observations,
                name,
                context,
                max_age_seconds=SAFETY_MAX_AGE_SECONDS.get(name),
                minimum_confidence=MINIMUM_SAFETY_INPUT_CONFIDENCE,
            )
            if metric is not None:
                selected = metric
                break
        if selected is None:
            return context.at
        expiry = safety_evidence_valid_until(selected)
        if expiry is None:
            return context.at
        expiries.append(expiry)

    for name in _ALWAYS_EVALUATED_SIGNALS - required_names:
        metric, _ = _current_metric(
            observations,
            name,
            context,
            max_age_seconds=SAFETY_MAX_AGE_SECONDS.get(name),
            minimum_confidence=MINIMUM_SAFETY_INPUT_CONFIDENCE,
        )
        if metric is None:
            continue
        expiry = safety_evidence_valid_until(metric)
        if expiry is None:
            return context.at
        expiries.append(expiry)

    return min(expiries) if expiries else context.at


def _requirements(context: EvaluationContext) -> tuple[Requirement, ...]:
    outdoor_alerts = (
        Requirement("safety.weather_alert.required", ("weather_alert_level",), "WEATHER_ALERT_MISSING"),
        Requirement(
            "safety.lightning.required",
            ("lightning_clearance_minutes",),
            "LIGHTNING_CLEARANCE_MISSING",
        ),
    )
    if context.activity is Activity.SWIM and context.environment is Environment.MARINE_BEACH:
        return (
            Requirement(
                "safety.access.required",
                ("official_entry_status", "access_status"),
                "ACCESS_STATUS_MISSING",
            ),
            *outdoor_alerts,
            Requirement("safety.rip.required", ("rip_current_risk",), "RIP_CURRENT_STATUS_MISSING"),
            Requirement("safety.water_quality.required", ("water_quality_status",), "WATER_QUALITY_STATUS_MISSING"),
            Requirement("safety.marine_hazard.required", ("marine_hazard_status",), "MARINE_HAZARD_STATUS_MISSING"),
            Requirement("safety.water_temperature.required", ("water_temperature_c",), "WATER_TEMPERATURE_MISSING"),
            *(
                (
                    Requirement("safety.patrol.required", ("patrol_status",), "PATROL_STATUS_MISSING"),
                    Requirement(
                        "safety.designated_swim_zone.required",
                        ("designated_swim_zone_status",),
                        "DESIGNATED_SWIM_ZONE_STATUS_MISSING",
                    ),
                    Requirement(
                        "safety.adult_supervision.required",
                        ("adult_supervision_status",),
                        "ADULT_SUPERVISION_STATUS_MISSING",
                    ),
                )
                if context.participant_profile in {"family", "beginner", "family_swim"}
                else ()
            ),
        )
    if context.activity is Activity.SWIM and context.environment is Environment.INLAND_WATER:
        return (
            Requirement(
                "safety.access.required",
                ("official_entry_status", "access_status"),
                "ACCESS_STATUS_MISSING",
            ),
            *outdoor_alerts,
            Requirement("safety.river.required", ("river_risk_level",), "RIVER_RISK_STATUS_MISSING"),
            Requirement("safety.water_quality.required", ("water_quality_status",), "WATER_QUALITY_STATUS_MISSING"),
        )
    if context.activity is Activity.SURF:
        return (
            Requirement(
                "safety.access.required",
                ("official_entry_status", "access_status"),
                "ACCESS_STATUS_MISSING",
            ),
            *outdoor_alerts,
            Requirement("safety.rip.required", ("rip_current_risk",), "RIP_CURRENT_STATUS_MISSING"),
            Requirement("safety.marine_hazard.required", ("marine_hazard_status",), "MARINE_HAZARD_STATUS_MISSING"),
        )
    if context.activity is Activity.MUDFLAT:
        return (
            Requirement(
                "safety.access.required",
                ("official_entry_status", "access_status"),
                "ACCESS_STATUS_MISSING",
            ),
            *outdoor_alerts,
            Requirement("safety.tide.required", ("tide_window_open",), "TIDE_WINDOW_MISSING"),
            Requirement("safety.marine_hazard.required", ("marine_hazard_status",), "MARINE_HAZARD_STATUS_MISSING"),
            Requirement("safety.fog.required", ("fog_status",), "FOG_STATUS_MISSING"),
            Requirement("safety.route.required", ("designated_route_status",), "DESIGNATED_ROUTE_STATUS_MISSING"),
        )
    if context.activity is Activity.RAFTING:
        return (
            Requirement("safety.operator.required", ("operator_status",), "OPERATOR_STATUS_MISSING"),
            *outdoor_alerts,
            Requirement("safety.river.required", ("river_risk_level",), "RIVER_RISK_STATUS_MISSING"),
            Requirement("safety.equipment.required", ("safety_equipment_status",), "SAFETY_EQUIPMENT_STATUS_MISSING"),
            Requirement("safety.upstream_rain.required", ("upstream_rain_risk",), "UPSTREAM_RAIN_STATUS_MISSING"),
        )
    if context.activity is Activity.ONSEN:
        return (
            Requirement("safety.facility.required", ("facility_status",), "FACILITY_STATUS_MISSING"),
            Requirement("safety.hygiene.required", ("facility_hygiene_status",), "FACILITY_HYGIENE_STATUS_MISSING"),
            Requirement("safety.hot_tub_temperature.required", ("hot_tub_temperature_c",), "HOT_TUB_TEMPERATURE_MISSING"),
        )
    if (
        context.activity is Activity.RELAX
        and context.environment is Environment.MARINE_BEACH
    ):
        return (
            Requirement(
                "safety.access.required",
                ("official_entry_status", "access_status"),
                "ACCESS_STATUS_MISSING",
            ),
            *outdoor_alerts,
            Requirement("safety.marine_hazard.required", ("marine_hazard_status",), "MARINE_HAZARD_STATUS_MISSING"),
        )
    return outdoor_alerts


def required_safety_metric_groups(
    context: EvaluationContext,
) -> tuple[tuple[str, ...], ...]:
    """Return the alternative metric groups required to clear safety gates.

    Consumers that project a persisted evaluation at a later time must use the
    same requirement grammar as the evaluator.  Keeping this as a small public
    projection avoids duplicating activity/profile rules at API boundaries.
    """

    return tuple(requirement.any_of for requirement in _requirements(context))


def _canonical(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _rule(metric: Metric, rule_id: str, severity: RuleSeverity, reason_code: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        severity=severity,
        metric_name=metric.name,
        reason_code=reason_code,
        source=metric.source,
        source_url=metric.source_url,
        observed_at=metric.observed_at,
    )


def _unknown_value(metric: Metric, rule_id: str) -> RuleResult:
    return _rule(metric, rule_id, RuleSeverity.UNKNOWN, "SAFETY_VALUE_UNRECOGNIZED")


def _signal_rules(metric: Metric, context: EvaluationContext) -> Iterable[RuleResult]:
    value = _canonical(metric.value)
    outdoor = context.activity is not Activity.ONSEN

    if metric.name == "official_stop_signal":
        if metric.value is True or value in {"true", "active", "stop", "1", "발효", "통제"}:
            yield _rule(metric, "safety.official_stop", RuleSeverity.BLOCK, "OFFICIAL_STOP_ACTIVE")
        elif metric.value is not False and value not in {"false", "clear", "none", "0", "해제", "없음"}:
            yield _unknown_value(metric, "safety.official_stop.unknown")
    elif metric.name in {"access_status", "official_entry_status"}:
        if value in {"closed", "restricted", "통제", "입수통제", "폐쇄"}:
            yield _rule(metric, "safety.access.closed", RuleSeverity.BLOCK, "OFFICIAL_ACCESS_CLOSED")
        elif value not in {"open", "allowed", "clear", "개방", "허용", "정상"}:
            yield _unknown_value(metric, "safety.access.unknown")
    elif metric.name in {"facility_status", "operator_status"}:
        if value in {"closed", "suspended", "restricted", "휴업", "운휴", "통제", "폐쇄"}:
            yield _rule(metric, f"safety.{metric.name}.closed", RuleSeverity.BLOCK, "OPERATION_NOT_AVAILABLE")
        elif value not in {"open", "active", "operating", "영업", "운영", "정상"}:
            yield _unknown_value(metric, f"safety.{metric.name}.unknown")
    elif metric.name == "lightning_clearance_minutes" and outdoor:
        try:
            clearance = float(metric.value)
        except (TypeError, ValueError):
            yield _unknown_value(metric, "safety.lightning.unknown")
            return
        if not math.isfinite(clearance) or clearance < 0:
            yield _unknown_value(metric, "safety.lightning.unknown")
        elif clearance < 30:
            yield _rule(metric, "safety.lightning.active", RuleSeverity.BLOCK, "LIGHTNING_30_MINUTE_CLEARANCE_NOT_MET")
    elif metric.name == "weather_alert_level" and outdoor:
        if value in {"warning", "emergency", "경보", "위험"}:
            yield _rule(metric, "safety.weather.block", RuleSeverity.BLOCK, "SEVERE_WEATHER_ALERT")
        elif value in {"advisory", "watch", "주의보", "주의"}:
            yield _rule(metric, "safety.weather.caution", RuleSeverity.CAUTION, "WEATHER_ADVISORY")
        elif value not in {"none", "clear", "normal", "없음", "해제", "정상", "0"}:
            yield _unknown_value(metric, "safety.weather.unknown")
    elif metric.name == "marine_hazard_status" and outdoor:
        if value in {
            "advisory", "warning", "danger", "emergency", "주의보", "경보",
            "주의", "경계", "위험", "태풍", "풍랑", "폭풍해일", "호우",
        }:
            yield _rule(metric, "safety.marine_hazard.block", RuleSeverity.BLOCK, "MARINE_HAZARD_ACTIVE")
        elif value not in {"clear", "none", "normal", "관심", "없음", "정상", "0"}:
            yield _unknown_value(metric, "safety.marine_hazard.unknown")
    elif metric.name == "rip_current_risk" and context.activity in {Activity.SWIM, Activity.SURF}:
        try:
            numeric_risk = float(metric.value)
        except (TypeError, ValueError):
            numeric_risk = None
        if numeric_risk is not None and not 0 <= numeric_risk <= 120:
            yield _unknown_value(metric, "safety.rip.out_of_range")
        elif (numeric_risk is not None and numeric_risk >= 55) or value in {
            "warning", "danger", "경계", "위험", "3", "4"
        }:
            yield _rule(metric, "safety.rip.block", RuleSeverity.BLOCK, "RIP_CURRENT_HIGH")
        elif (numeric_risk is not None and numeric_risk >= 30) or value in {"caution", "주의", "2"}:
            yield _rule(metric, "safety.rip.caution", RuleSeverity.CAUTION, "RIP_CURRENT_CAUTION")
        elif numeric_risk is None and value not in {"attention", "관심", "1", "clear", "none"}:
            yield _unknown_value(metric, "safety.rip.unknown")
    elif metric.name == "water_temperature_c" and context.activity is Activity.SWIM:
        if context.participant_profile in {"family", "beginner", "family_swim"}:
            try:
                water_temperature = float(metric.value)
            except (TypeError, ValueError):
                yield _unknown_value(metric, "safety.family_water_temperature.unknown")
                return
            if not math.isfinite(water_temperature):
                yield _unknown_value(metric, "safety.family_water_temperature.unknown")
            elif water_temperature < 15 or water_temperature > 31:
                yield _rule(
                    metric,
                    "safety.family_water_temperature.block",
                    RuleSeverity.BLOCK,
                    "FAMILY_SWIM_WATER_TEMPERATURE_OUTSIDE_POLICY",
                )
            elif water_temperature < 18:
                yield _rule(
                    metric,
                    "safety.family_water_temperature.caution",
                    RuleSeverity.CAUTION,
                    "FAMILY_SWIM_COLD_WATER_CAUTION",
                )
    elif metric.name == "patrol_status" and context.activity is Activity.SWIM:
        if context.participant_profile in {"family", "beginner", "family_swim"}:
            if value in {"inactive", "off_duty", "absent", "미운영", "미배치", "없음"}:
                yield _rule(metric, "safety.patrol.caution", RuleSeverity.CAUTION, "ACTIVE_PATROL_UNAVAILABLE")
            elif value not in {"active", "patrolled", "verified", "운영", "배치", "확인"}:
                yield _unknown_value(metric, "safety.patrol.unknown")
    elif metric.name == "designated_swim_zone_status" and context.activity is Activity.SWIM:
        if context.participant_profile in {"family", "beginner", "family_swim"}:
            if value in {"closed", "unavailable", "outside", "폐쇄", "없음", "구역밖"}:
                yield _rule(metric, "safety.designated_swim_zone.block", RuleSeverity.BLOCK, "DESIGNATED_SWIM_ZONE_UNAVAILABLE")
            elif value not in {"open", "verified", "inside", "운영", "확인", "구역내"}:
                yield _unknown_value(metric, "safety.designated_swim_zone.unknown")
    elif metric.name == "adult_supervision_status" and context.activity is Activity.SWIM:
        if context.participant_profile in {"family", "beginner", "family_swim"}:
            if value in {"unavailable", "absent", "no", "false", "불가", "없음", "미확보"}:
                yield _rule(metric, "safety.adult_supervision.block", RuleSeverity.BLOCK, "ADULT_ARM_REACH_SUPERVISION_UNAVAILABLE")
            elif value not in {"confirmed", "available", "yes", "true", "확인", "가능", "확보"}:
                yield _unknown_value(metric, "safety.adult_supervision.unknown")
    elif metric.name == "water_quality_status" and context.activity in {
        Activity.SWIM,
        Activity.SURF,
        Activity.MUDFLAT,
        Activity.RAFTING,
    }:
        if value in {"fail", "closed", "unsafe", "부적합", "폐쇄"}:
            yield _rule(metric, "safety.water_quality.block", RuleSeverity.BLOCK, "WATER_QUALITY_UNSAFE")
        elif value in {"advisory", "caution", "주의", "권고", "입수자제"}:
            yield _rule(metric, "safety.water_quality.block", RuleSeverity.BLOCK, "WATER_QUALITY_ADVISORY")
        elif value not in {"pass", "suitable", "clear", "적합", "정상"}:
            yield _unknown_value(metric, "safety.water_quality.unknown")
    elif metric.name == "river_risk_level" and context.activity in {Activity.SWIM, Activity.RAFTING}:
        if value in {"warning", "danger", "경계", "위험", "3", "4"}:
            yield _rule(metric, "safety.river.block", RuleSeverity.BLOCK, "RIVER_CONDITIONS_DANGEROUS")
        elif value in {"caution", "주의", "2"}:
            yield _rule(metric, "safety.river.caution", RuleSeverity.CAUTION, "RIVER_CONDITIONS_CAUTION")
        elif value not in {"normal", "clear", "관심", "정상", "1"}:
            yield _unknown_value(metric, "safety.river.unknown")
    elif metric.name == "tide_window_open" and context.activity is Activity.MUDFLAT:
        if metric.value is False or value in {"false", "closed", "0", "종료", "불가"}:
            yield _rule(metric, "safety.tide.closed", RuleSeverity.BLOCK, "OUTSIDE_OFFICIAL_TIDE_WINDOW")
        elif metric.value is not True and value not in {"true", "open", "1", "가능", "운영"}:
            yield _unknown_value(metric, "safety.tide.unknown")
    elif metric.name == "fog_status" and context.activity is Activity.MUDFLAT:
        if value in {"fog", "active", "true", "1", "안개", "발생"}:
            yield _rule(metric, "safety.fog.block", RuleSeverity.BLOCK, "FOG_REQUIRES_EXIT")
        elif value not in {"clear", "none", "false", "0", "없음", "맑음"}:
            yield _unknown_value(metric, "safety.fog.unknown")
    elif metric.name == "designated_route_status" and context.activity is Activity.MUDFLAT:
        if value in {"closed", "unverified", "blocked", "폐쇄", "미확인", "통제"}:
            yield _rule(metric, "safety.route.block", RuleSeverity.BLOCK, "DESIGNATED_ROUTE_UNVERIFIED")
        elif value not in {"verified", "open", "확인", "개방"}:
            yield _unknown_value(metric, "safety.route.unknown")
    elif metric.name == "facility_hygiene_status" and context.activity is Activity.ONSEN:
        if value in {"fail", "restricted", "action", "부적합", "조치중", "이용제한"}:
            yield _rule(metric, "safety.hygiene.block", RuleSeverity.BLOCK, "FACILITY_HYGIENE_RESTRICTED")
        elif value not in {"pass", "clear", "suitable", "적합", "정상"}:
            yield _unknown_value(metric, "safety.hygiene.unknown")
    elif metric.name == "hot_tub_temperature_c" and context.activity is Activity.ONSEN:
        try:
            temperature = float(metric.value)
        except (TypeError, ValueError):
            yield _unknown_value(metric, "safety.hot_tub_temperature.unknown")
            return
        if not math.isfinite(temperature):
            yield _unknown_value(metric, "safety.hot_tub_temperature.unknown")
        elif temperature > 40.0:
            yield _rule(metric, "safety.hot_tub_temperature.block", RuleSeverity.BLOCK, "HOT_TUB_ABOVE_40C")
    elif metric.name == "safety_equipment_status" and context.activity is Activity.RAFTING:
        if value in {"missing", "failed", "unavailable", "미비", "없음", "불가"}:
            yield _rule(metric, "safety.equipment.block", RuleSeverity.BLOCK, "SAFETY_EQUIPMENT_UNVERIFIED")
        elif value not in {"verified", "ready", "확인", "준비"}:
            yield _unknown_value(metric, "safety.equipment.unknown")
    elif metric.name == "upstream_rain_risk" and context.activity is Activity.RAFTING:
        if value in {"caution", "warning", "danger", "주의", "경계", "위험", "1", "2", "3", "4"}:
            yield _rule(metric, "safety.upstream_rain.block", RuleSeverity.BLOCK, "UPSTREAM_RAIN_RISK")
        elif value not in {"none", "normal", "clear", "없음", "정상", "0"}:
            yield _unknown_value(metric, "safety.upstream_rain.unknown")


def _current_metric(
    observations: ObservationSet,
    name: str,
    context: EvaluationContext,
    *,
    max_age_seconds: int | None,
    minimum_confidence: float = 0.0,
) -> tuple[Metric | None, str | None]:
    metric = observations.get(name)
    if metric is None:
        return None, "missing"
    if not metric.is_current(context.at, max_age_seconds=max_age_seconds):
        return None, "stale_or_conflicting"
    if metric.confidence < minimum_confidence:
        return None, "low_confidence"
    return metric, None


def _evaluate_requirements(
    observations: ObservationSet, context: EvaluationContext
) -> tuple[list[RuleResult], set[str], set[str]]:
    results: list[RuleResult] = []
    missing: set[str] = set()
    stale: set[str] = set()
    evaluated_names: set[str] = set()
    for requirement in _requirements(context):
        current: Metric | None = None
        failure_kinds: list[str] = []
        for name in requirement.any_of:
            candidate, failure = _current_metric(
                observations,
                name,
                context,
                max_age_seconds=SAFETY_MAX_AGE_SECONDS.get(name),
                minimum_confidence=MINIMUM_SAFETY_INPUT_CONFIDENCE,
            )
            if candidate is not None:
                current = candidate
                break
            if failure is not None:
                failure_kinds.append(failure)
        if current is None:
            target = "|".join(requirement.any_of)
            if any(
                failure in {"stale_or_conflicting", "low_confidence"}
                for failure in failure_kinds
            ):
                stale.add(target)
            else:
                missing.add(target)
            results.append(
                RuleResult(
                    rule_id=requirement.rule_id,
                    severity=RuleSeverity.UNKNOWN,
                    metric_name=target,
                    reason_code=requirement.reason_code,
                )
            )
            continue
        evaluated_names.add(current.name)
        results.extend(_signal_rules(current, context))
    for name in _ALWAYS_EVALUATED_SIGNALS - evaluated_names:
        metric, _ = _current_metric(
            observations,
            name,
            context,
            max_age_seconds=SAFETY_MAX_AGE_SECONDS.get(name),
            minimum_confidence=MINIMUM_SAFETY_INPUT_CONFIDENCE,
        )
        if metric is not None:
            results.extend(_signal_rules(metric, context))
    return results, missing, stale


def _evaluate_score(
    observations: ObservationSet,
    context: EvaluationContext,
    profile: ScoreProfile,
) -> tuple[
    int | None,
    tuple[float, float] | None,
    float,
    float,
    list[Contribution],
    set[str],
    set[str],
]:
    contributions: list[Contribution] = []
    missing: set[str] = set()
    stale: set[str] = set()
    present_weight = 0.0
    confidence_points = 0.0
    factor_values: dict[str, Metric] = {}

    for factor in profile.factors:
        metric, failure = _current_metric(
            observations,
            factor.metric_name,
            context,
            max_age_seconds=factor.max_age_seconds,
        )
        if metric is None:
            if failure == "missing":
                missing.add(factor.metric_name)
            else:
                stale.add(factor.metric_name)
            continue
        try:
            normalized = float(factor.scorer(metric.value))
            if not math.isfinite(normalized) or not 0.0 <= normalized <= 100.0:
                raise ValueError("factor score must be finite and in range")
        except (TypeError, ValueError):
            stale.add(factor.metric_name)
            continue
        factor_values[factor.metric_name] = metric
        present_weight += factor.weight
        confidence_points += factor.weight * metric.confidence
        contributions.append(
            Contribution(
                metric_name=factor.metric_name,
                normalized_score=round(normalized, 2),
                configured_weight=factor.weight,
                effective_weight=0.0,
                weighted_points=0.0,
                evidence_basis=factor.evidence_basis,
                source=metric.source,
                source_url=metric.source_url,
                observed_at=metric.observed_at,
                mode=metric.mode,
            )
        )

    required_missing = []
    for group in profile.required_factor_groups:
        if not any(name in factor_values for name in group):
            required_missing.append("|".join(group))
    missing.update(required_missing)

    coverage = round(present_weight, 4)
    confidence = round(confidence_points, 4)
    lower_bound = sum(
        contribution.normalized_score * contribution.configured_weight
        for contribution in contributions
    )
    upper_bound = min(100.0, lower_bound + (1.0 - present_weight) * 100.0)
    score_range = (round(lower_bound, 2), round(upper_bound, 2))
    if (
        required_missing
        or present_weight < profile.minimum_coverage
        or confidence < profile.minimum_confidence
        or present_weight <= 0
    ):
        return None, score_range, confidence, coverage, contributions, missing, stale

    fixed_contributions: list[Contribution] = []
    for contribution in contributions:
        effective_weight = contribution.configured_weight
        weighted_points = contribution.normalized_score * effective_weight
        fixed_contributions.append(
            Contribution(
                metric_name=contribution.metric_name,
                normalized_score=contribution.normalized_score,
                configured_weight=contribution.configured_weight,
                effective_weight=round(effective_weight, 4),
                weighted_points=round(weighted_points, 2),
                evidence_basis=contribution.evidence_basis,
                source=contribution.source,
                source_url=contribution.source_url,
                observed_at=contribution.observed_at,
                mode=contribution.mode,
            )
        )
    return (
        math.floor(lower_bound),
        score_range,
        confidence,
        coverage,
        fixed_contributions,
        missing,
        stale,
    )


def evaluate_water_index(
    observations: ObservationSet,
    context: EvaluationContext,
) -> IndexResult:
    """Evaluate one activity without ever converting uncertainty into safety."""

    profile = PROFILES[context.activity]
    surf_assessment: SurfSkillEvidenceAssessment | None = None
    score_observations = observations
    if context.activity is Activity.SURF:
        surf_assessment = assess_surf_skill_evidence(
            observations,
            participant_skill_level=context.participant_skill_level,
            at=context.at,
        )
        if not surf_assessment.matched:
            # The raw KHOA evidence remains available for audit/re-evaluation,
            # but an unscoped or mismatched grade cannot enter the suitability
            # calculation for this participant identity.
            score_observations = ObservationSet(
                {
                    name: metric
                    for name, metric in observations.metrics.items()
                    if name
                    not in {
                        "official_activity_grade",
                        "official_activity_score",
                    }
                }
            )

    safety_gates, safety_missing, safety_stale = _evaluate_requirements(
        observations,
        context,
    )
    (
        score,
        score_range,
        confidence,
        coverage,
        contributions,
        factor_missing,
        factor_stale,
    ) = _evaluate_score(score_observations, context, profile)

    suitability_gates: tuple[RuleResult, ...] = ()
    if surf_assessment is not None and not surf_assessment.matched:
        factor_missing.discard("official_activity_grade")
        reason_code = surf_assessment.reason_code
        if reason_code == SURF_SKILL_LEVEL_REQUIRED:
            metric_name = "participant_skill_level"
            factor_missing.add(metric_name)
        elif reason_code == SURF_OFFICIAL_GRADE_MISSING:
            metric_name = "official_activity_grade"
            factor_missing.add(metric_name)
        elif reason_code == SURF_GRADE_DETAIL_MISSING:
            metric_name = "official_grade_detail"
            factor_missing.add(metric_name)
        else:
            metric_name = "official_grade_detail"
            factor_stale.add(metric_name)
        suitability_gates = (
            RuleResult(
                rule_id="suitability.surf.skill_grade",
                severity=RuleSeverity.UNKNOWN,
                metric_name=metric_name,
                reason_code=reason_code,
            ),
        )

    # Suitability uncertainty must suppress the score/decision without claiming
    # that independently complete hazard gates are themselves unknown.
    has_block = any(gate.severity is RuleSeverity.BLOCK for gate in safety_gates)
    has_unknown = any(gate.severity is RuleSeverity.UNKNOWN for gate in safety_gates)
    has_caution = any(gate.severity is RuleSeverity.CAUTION for gate in safety_gates)

    if has_block:
        safety_status = SafetyStatus.STOP
        decision = Decision.BLOCKED
        public_score = None
        public_score_range = None
    elif has_unknown:
        safety_status = SafetyStatus.UNKNOWN
        decision = Decision.UNKNOWN
        public_score = None
        public_score_range = None
    elif has_caution:
        safety_status = SafetyStatus.CAUTION
        decision = Decision.CAUTION
        public_score = min(score, 39) if score is not None else None
        public_score_range = (
            (min(score_range[0], 39), min(score_range[1], 39))
            if score_range is not None
            else None
        )
    elif score is None:
        safety_status = SafetyStatus.CLEAR
        decision = Decision.UNKNOWN
        public_score = None
        public_score_range = score_range
    elif score >= 80:
        safety_status = SafetyStatus.CLEAR
        decision = Decision.RECOMMENDED
        public_score = score
        public_score_range = score_range
    elif score >= 60:
        safety_status = SafetyStatus.CLEAR
        decision = Decision.CONSIDER
        public_score = score
        public_score_range = score_range
    else:
        safety_status = SafetyStatus.CLEAR
        decision = Decision.NOT_RECOMMENDED
        public_score = score
        public_score_range = score_range

    if surf_assessment is not None and not surf_assessment.matched:
        # A numeric uncertainty interval is still a participant suitability
        # claim. Do not publish [0, 100] (or any narrower range) when the KHOA
        # GrdCn evidence is not valid for this exact skill identity.
        public_score = None
        public_score_range = None
        if safety_status is SafetyStatus.CLEAR:
            decision = Decision.UNKNOWN

    return IndexResult(
        methodology_version=METHODOLOGY_VERSION,
        activity=context.activity,
        environment=context.environment,
        safety_status=safety_status,
        decision=decision,
        score=public_score,
        score_range=public_score_range,
        confidence=confidence,
        coverage=coverage,
        evaluated_at=context.at,
        gates=(*safety_gates, *suitability_gates),
        contributions=tuple(contributions),
        missing_metrics=tuple(sorted(safety_missing | factor_missing)),
        stale_or_conflicting_metrics=tuple(sorted(safety_stale | factor_stale)),
        limitations=profile.limitations,
    )
