"""Interpretable continuous-preference scoring with fail-closed hard gates."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .domain import (
    Candidate,
    CandidateAssessment,
    GateValue,
    RecommendationRequest,
    ScoreContribution,
)


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Configuration for uncertainty, never for mandatory safety decisions."""

    uncertainty_penalty_rate: float = 0.35

    def __post_init__(self) -> None:
        if not math.isfinite(self.uncertainty_penalty_rate):
            raise ValueError("uncertainty_penalty_rate must be finite")
        if not 0.0 <= self.uncertainty_penalty_rate <= 1.0:
            raise ValueError("uncertainty_penalty_rate must be between 0 and 1")


def _gate_reasons(candidate: Candidate, request: RecommendationRequest) -> tuple[str, ...]:
    """Return all mandatory-gate failures in a stable, explainable order."""

    reasons: list[str] = []

    if candidate.safety is GateValue.DENY:
        reasons.append("SAFETY_BLOCKED")
    elif candidate.safety is GateValue.UNKNOWN:
        reasons.append("SAFETY_UNKNOWN")

    if candidate.operation is GateValue.DENY:
        reasons.append("OPERATION_CLOSED")
    elif candidate.operation is GateValue.UNKNOWN:
        reasons.append("OPERATION_UNKNOWN")

    if request.party.requires_accessibility:
        if candidate.accessibility is GateValue.DENY:
            reasons.append("ACCESSIBILITY_UNAVAILABLE")
        elif candidate.accessibility is GateValue.UNKNOWN:
            reasons.append("ACCESSIBILITY_UNKNOWN")

    if request.party.bringing_pet:
        if candidate.pet_policy is GateValue.DENY:
            reasons.append("PET_NOT_ALLOWED")
        elif candidate.pet_policy is GateValue.UNKNOWN:
            reasons.append("PET_POLICY_UNKNOWN")

    if not candidate.age_policy.known:
        reasons.append("AGE_POLICY_UNKNOWN")
    else:
        if any(age < candidate.age_policy.minimum_age for age in request.party.ages):
            reasons.append("AGE_BELOW_MINIMUM")
        maximum = candidate.age_policy.maximum_age
        if maximum is not None and any(age > maximum for age in request.party.ages):
            reasons.append("AGE_ABOVE_MAXIMUM")

    return tuple(reasons)


class RecommendationEngine:
    """Pure scoring engine whose output depends only on explicit input evidence.

    Persona labels are deliberately not read here.  A user is represented for
    matching by a continuous preference vector; a persona remains display-only.
    """

    def __init__(self, policy: ScoringPolicy | None = None) -> None:
        self._policy = policy or ScoringPolicy()

    @property
    def policy(self) -> ScoringPolicy:
        return self._policy

    def assess(
        self,
        candidate: Candidate,
        request: RecommendationRequest,
    ) -> CandidateAssessment:
        gate_reasons = _gate_reasons(candidate, request)
        if gate_reasons:
            return CandidateAssessment(
                candidate=candidate,
                hard_gate_passed=False,
                score=None,
                base_score=None,
                uncertainty_penalty=0.0,
                effective_confidence=0.0,
                preference_coverage=0.0,
                gate_reasons=gate_reasons,
                reason_codes=gate_reasons,
            )

        contributions: list[ScoreContribution] = []
        present_weight = 0.0
        weighted_similarity = 0.0
        for target in request.preferences.targets:
            candidate_value = candidate.features.get(target.feature)
            if candidate_value is None:
                continue
            similarity = 1.0 - abs(target.target - candidate_value)
            weighted_points = target.weight * similarity * 100.0
            present_weight += target.weight
            weighted_similarity += weighted_points
            contributions.append(
                ScoreContribution(
                    feature=target.feature,
                    reason_code=f"PREFERENCE_MATCH_{target.feature.upper()}",
                    target=target.target,
                    candidate_value=candidate_value,
                    similarity=round(similarity, 6),
                    configured_weight=target.weight,
                    weighted_points=round(weighted_points, 6),
                )
            )

        if present_weight == 0.0:
            return CandidateAssessment(
                candidate=candidate,
                hard_gate_passed=True,
                score=None,
                base_score=None,
                uncertainty_penalty=0.0,
                effective_confidence=0.0,
                preference_coverage=0.0,
                reason_codes=("PREFERENCE_EVIDENCE_MISSING",),
            )

        coverage = present_weight / request.preferences.total_weight
        base_score = weighted_similarity / present_weight
        effective_confidence = candidate.evidence_confidence * coverage
        uncertainty_penalty = (
            base_score
            * self._policy.uncertainty_penalty_rate
            * (1.0 - effective_confidence)
        )
        final_score = max(0.0, min(100.0, base_score - uncertainty_penalty))
        reason_codes = [item.reason_code for item in contributions]
        if uncertainty_penalty > 0.0:
            reason_codes.append("UNCERTAINTY_PENALTY")

        return CandidateAssessment(
            candidate=candidate,
            hard_gate_passed=True,
            score=round(final_score, 6),
            base_score=round(base_score, 6),
            uncertainty_penalty=round(uncertainty_penalty, 6),
            effective_confidence=round(effective_confidence, 6),
            preference_coverage=round(coverage, 6),
            reason_codes=tuple(reason_codes),
            contributions=tuple(contributions),
        )

    def assess_all(
        self,
        candidates: tuple[Candidate, ...],
        request: RecommendationRequest,
    ) -> tuple[CandidateAssessment, ...]:
        ids = tuple(candidate.spot_id for candidate in candidates)
        if len(ids) != len(set(ids)):
            raise ValueError("candidate spot_id values must be unique")
        return tuple(self.assess(candidate, request) for candidate in candidates)
