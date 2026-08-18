"""Exact, evidence-bound KHOA surfing grade/participant skill matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .domain import Metric, MetricState, ObservationSet


CONCRETE_SURF_SKILL_LEVELS = ("beginner", "intermediate", "advanced")
SURF_SKILL_LEVEL_UNSPECIFIED = "unspecified"

SURF_SKILL_LEVEL_REQUIRED = "SURF_SKILL_LEVEL_REQUIRED"
SURF_OFFICIAL_GRADE_MISSING = "SURF_OFFICIAL_GRADE_MISSING"
SURF_GRADE_DETAIL_MISSING = "SURF_GRADE_DETAIL_MISSING"
SURF_GRADE_EVIDENCE_NOT_AUTHORITATIVE = (
    "SURF_GRADE_EVIDENCE_NOT_AUTHORITATIVE"
)
SURF_GRADE_EVIDENCE_SCOPE_MISMATCH = (
    "SURF_GRADE_EVIDENCE_SCOPE_MISMATCH"
)
SURF_GRADE_DETAIL_UNSUPPORTED = "SURF_GRADE_DETAIL_UNSUPPORTED"
SURF_GRADE_SKILL_MISMATCH = "SURF_GRADE_SKILL_MISMATCH"

_SURF_GRADE_SKILL_SCOPES = {
    # This is the sole KHOA GrdCn shape evidenced by the provider contract
    # fixture. Free-form or merely similar prose is never expanded into a skill
    # claim. Whitespace is canonicalized because provider XML formatting is not
    # semantically meaningful.
    "초중급자에게적합": frozenset({"beginner", "intermediate"}),
}


@dataclass(frozen=True, slots=True)
class SurfSkillEvidenceAssessment:
    matched: bool
    reason_code: str
    participant_skill_level: str
    grade_detail: str = ""


def assess_surf_skill_evidence(
    observations: ObservationSet | Iterable[Metric],
    *,
    participant_skill_level: object,
    at: datetime,
) -> SurfSkillEvidenceAssessment:
    """Match only a current, co-scoped KHOA grade/detail evidence pair."""

    skill_level = canonical_participant_skill_level(participant_skill_level)
    if skill_level not in CONCRETE_SURF_SKILL_LEVELS:
        return SurfSkillEvidenceAssessment(
            matched=False,
            reason_code=SURF_SKILL_LEVEL_REQUIRED,
            participant_skill_level=skill_level,
        )

    metrics = (
        observations.metrics.values()
        if isinstance(observations, ObservationSet)
        else observations
    )
    by_name = {metric.name: metric for metric in metrics}
    grade = by_name.get("official_activity_grade")
    detail = by_name.get("official_grade_detail")
    if grade is None:
        return SurfSkillEvidenceAssessment(
            False,
            SURF_OFFICIAL_GRADE_MISSING,
            skill_level,
        )
    if detail is None:
        return SurfSkillEvidenceAssessment(
            False,
            SURF_GRADE_DETAIL_MISSING,
            skill_level,
        )
    if not _authoritative_current_text(grade, at=at) or not (
        _authoritative_current_text(detail, at=at)
    ):
        return SurfSkillEvidenceAssessment(
            False,
            SURF_GRADE_EVIDENCE_NOT_AUTHORITATIVE,
            skill_level,
        )
    if _evidence_identity(grade) != _evidence_identity(detail):
        return SurfSkillEvidenceAssessment(
            False,
            SURF_GRADE_EVIDENCE_SCOPE_MISMATCH,
            skill_level,
            str(detail.value),
        )

    canonical_detail = "".join(str(detail.value).split()).casefold()
    allowed_skills = _SURF_GRADE_SKILL_SCOPES.get(canonical_detail)
    if allowed_skills is None:
        return SurfSkillEvidenceAssessment(
            False,
            SURF_GRADE_DETAIL_UNSUPPORTED,
            skill_level,
            str(detail.value),
        )
    if skill_level not in allowed_skills:
        return SurfSkillEvidenceAssessment(
            False,
            SURF_GRADE_SKILL_MISMATCH,
            skill_level,
            str(detail.value),
        )
    return SurfSkillEvidenceAssessment(
        True,
        "",
        skill_level,
        str(detail.value),
    )


def canonical_participant_skill_level(value: object) -> str:
    raw = getattr(value, "value", value)
    canonical = str(raw).strip().lower()
    if canonical not in {
        *CONCRETE_SURF_SKILL_LEVELS,
        SURF_SKILL_LEVEL_UNSPECIFIED,
    }:
        raise ValueError(
            "participant_skill_level must be beginner, intermediate, "
            "advanced, or unspecified"
        )
    return canonical


def _authoritative_current_text(metric: Metric, *, at: datetime) -> bool:
    return (
        metric.source.strip().upper() == "KHOA"
        and metric.state is MetricState.VALID
        and isinstance(metric.value, str)
        and bool(metric.value.strip())
        and metric.is_current(at, max_age_seconds=43_200)
    )


def _evidence_identity(metric: Metric) -> tuple[object, ...]:
    return (
        metric.source.strip().upper(),
        metric.source_url,
        metric.station_id,
        metric.spatial_scope,
        metric.observed_at,
        metric.fetched_at,
        metric.valid_from,
        metric.valid_until,
        metric.mode,
    )
