"""Django catalog boundary for the pure recommendation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from services.ingestion.fusion import FUSION_PROVIDER, environment_for_spot
from services.ingestion.participant_profiles import FAMILY_PROFILE, GENERAL_PROFILE
from services.water_index import (
    Activity,
    EvaluationContext,
    IndexResult,
    Metric,
    MetricMode,
    MetricState,
    METHODOLOGY_VERSION,
    ObservationSet,
    SAFETY_MAX_AGE_SECONDS,
    evaluate_water_index,
)

from .diversity import MMRSelector
from .domain import (
    AgePolicy,
    Candidate,
    CandidateAssessment,
    FeatureValue,
    FeatureVector,
    GateValue,
    ParticipantSkillLevel,
    RankedRecommendation,
    RecommendationRequest,
    TimeWindow,
)
from .scoring import RecommendationEngine


MAX_CONDITION_AGE = timedelta(minutes=15)
MINOR_AGE_CUTOFF = 19
@dataclass(frozen=True, slots=True)
class CatalogEvidence:
    spot: Any
    candidate: Candidate
    condition_score: Any | None
    current_evaluation: IndexResult | None
    session_context_used: bool


@dataclass(frozen=True, slots=True)
class CatalogRecommendationResult:
    ranked: tuple[RankedRecommendation, ...]
    assessments: tuple[CandidateAssessment, ...]
    evidence: tuple[CatalogEvidence, ...]
    evaluated_at: datetime
    activity: str
    participant_profile: str
    participant_skill_level: str

    def evidence_for(self, spot_id: str) -> CatalogEvidence:
        for item in self.evidence:
            if item.candidate.spot_id == spot_id:
                return item
        raise KeyError(spot_id)


class DatabaseRecommendationService:
    """Build candidates only from explicit catalog and fused condition evidence."""

    def __init__(
        self,
        *,
        engine: RecommendationEngine | None = None,
        selector: MMRSelector | None = None,
    ) -> None:
        self._engine = engine or RecommendationEngine()
        self._selector = selector or MMRSelector()

    def recommend(
        self,
        *,
        spots: Iterable[Any],
        activity: str,
        request: RecommendationRequest,
        limit: int,
        at: datetime,
    ) -> CatalogRecommendationResult:
        _require_aware(at)
        selected_spots = tuple(spots)
        participant_profile = _participant_profile(request, activity=activity)
        score_by_spot = _latest_condition_scores(
            selected_spots,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=request.party.participant_skill_level,
            at=at,
        )
        evidence = tuple(
            _catalog_evidence(
                spot,
                activity=activity,
                participant_profile=participant_profile,
                adult_supervision_confirmed=(
                    request.party.adult_supervision_confirmed
                ),
                participant_skill_level=request.party.participant_skill_level,
                condition_score=score_by_spot.get(spot.pk),
                at=at,
            )
            for spot in selected_spots
        )
        candidates = tuple(item.candidate for item in evidence)
        assessments = self._engine.assess_all(candidates, request)
        ranked = self._selector.select(assessments, limit)
        return CatalogRecommendationResult(
            ranked=ranked,
            assessments=assessments,
            evidence=evidence,
            evaluated_at=at,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=request.party.participant_skill_level.value,
        )


def _latest_condition_scores(
    spots: tuple[Any, ...],
    *,
    activity: str,
    participant_profile: str,
    participant_skill_level: ParticipantSkillLevel,
    at: datetime,
) -> dict[int, Any]:
    if not spots:
        return {}
    requested_skill = (
        participant_skill_level.value
        if activity == Activity.SURF.value
        else ParticipantSkillLevel.UNSPECIFIED.value
    )
    selected = _condition_scores_for_skill(
        spots,
        activity=activity,
        participant_profile=participant_profile,
        participant_skill_level=requested_skill,
        at=at,
    )
    if (
        activity == Activity.SURF.value
        and requested_skill != ParticipantSkillLevel.UNSPECIFIED.value
        and len(selected) < len(spots)
    ):
        missing_spots = tuple(
            spot for spot in spots if spot.pk not in selected
        )
        selected.update(
            _condition_scores_for_skill(
                missing_spots,
                activity=activity,
                participant_profile=participant_profile,
                participant_skill_level=(
                    ParticipantSkillLevel.UNSPECIFIED.value
                ),
                at=at,
            )
        )
    return selected


def _condition_scores_for_skill(
    spots: tuple[Any, ...],
    *,
    activity: str,
    participant_profile: str,
    participant_skill_level: str,
    at: datetime,
) -> dict[int, Any]:
    if not spots:
        return {}
    from apps.conditions.models import ConditionScore
    from django.db.models import F, OuterRef, Subquery

    latest_id = (
        ConditionScore.objects.filter(
            spot_id=OuterRef("spot_id"),
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            snapshot__provider=FUSION_PROVIDER,
            snapshot__spot_id=F("spot_id"),
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at__lte=at,
        )
        .order_by("-evaluated_at", "-id")
        .values("id")[:1]
    )
    rows = (
        ConditionScore.objects.select_related("snapshot", "spot")
        .prefetch_related("snapshot__metrics")
        .filter(
            spot_id__in=[spot.pk for spot in spots],
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            snapshot__provider=FUSION_PROVIDER,
            snapshot__spot_id=F("spot_id"),
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at__lte=at,
            id=Subquery(latest_id),
        )
        .order_by("spot_id")
    )
    return {score.spot_id: score for score in rows}


def _catalog_evidence(
    spot: Any,
    *,
    activity: str,
    participant_profile: str,
    adult_supervision_confirmed: bool | None,
    participant_skill_level: ParticipantSkillLevel,
    condition_score: Any | None,
    at: datetime,
) -> CatalogEvidence:
    current_evaluation = _revalidate_condition_score(
        condition_score,
        spot=spot,
        activity=activity,
        participant_profile=participant_profile,
        adult_supervision_confirmed=adult_supervision_confirmed,
        participant_skill_level=participant_skill_level,
        at=at,
    )
    time_windows = _time_windows(getattr(spot, "opening_windows", None))
    cost_minor = _cost_minor(getattr(spot, "cost_krw", None))
    operation = _operation_gate(condition_score, activity=activity, at=at)
    if operation is not GateValue.DENY and (
        not time_windows or cost_minor is None
    ):
        operation = GateValue.UNKNOWN
    features = _feature_vector(getattr(spot, "preference_features", {}))
    if (
        current_evaluation is not None
        and current_evaluation.score is not None
        and current_evaluation.safety_status.value == "clear"
    ):
        features = _with_feature(
            features,
            FeatureValue(
                "water_suitability",
                float(current_evaluation.score) / 100.0,
            ),
        )
    confidence = _evidence_confidence(spot, current_evaluation)
    candidate = Candidate(
        spot_id=str(spot.pk),
        name=spot.name,
        activity=activity,
        region=spot.region or "unknown",
        features=features,
        time_windows=time_windows,
        duration_minutes=max(1, int(getattr(spot, "typical_duration_minutes", 60))),
        cost_minor=cost_minor,
        safety=_safety_gate(condition_score, current_evaluation),
        operation=operation,
        accessibility=_accessibility_gate(spot),
        pet_policy=_pet_gate(spot),
        age_policy=_age_policy(spot),
        evidence_confidence=confidence,
        diversity_tags=frozenset(_safe_tags(getattr(spot, "tags", []))),
        indoor=bool(getattr(spot, "indoor", False)),
        bad_weather_suitable=(
            bool(getattr(spot, "bad_weather_suitable", False))
            and getattr(spot, "catalog_verification", "unknown") == "verified"
        ),
    )
    return CatalogEvidence(
        spot=spot,
        candidate=candidate,
        condition_score=condition_score,
        current_evaluation=current_evaluation,
        session_context_used=(
            participant_profile == FAMILY_PROFILE
            and activity == Activity.SWIM.value
            and adult_supervision_confirmed is not None
        ),
    )


def _feature_vector(raw: Any) -> FeatureVector:
    values: list[FeatureValue] = []
    if isinstance(raw, dict):
        for name, value in sorted(raw.items()):
            try:
                if isinstance(value, bool):
                    continue
                values.append(FeatureValue(str(name), float(value)))
            except (TypeError, ValueError):
                continue
    return FeatureVector(tuple(values))


def _with_feature(vector: FeatureVector, feature: FeatureValue) -> FeatureVector:
    retained = tuple(
        item for item in vector.values if item.feature != feature.feature
    )
    return FeatureVector((*retained, feature))


def _time_windows(raw: Any) -> tuple[TimeWindow, ...]:
    windows: list[TimeWindow] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                windows.append(
                    TimeWindow(
                        int(item["start_minute"]),
                        int(item["end_minute"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return tuple(windows)


def _cost_minor(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value >= 0 else None


def _safety_gate(
    score: Any | None,
    current_evaluation: IndexResult | None,
) -> GateValue:
    if score is None:
        return GateValue.UNKNOWN
    # A recorded stop/caution remains a denial even after its clearing inputs
    # become stale. Fresh evidence can only be established by a new evaluation.
    if score.safety_status in {"stop", "caution"}:
        return GateValue.DENY
    if score.decision == "not_recommended":
        return GateValue.DENY
    if current_evaluation is None:
        return GateValue.UNKNOWN
    if current_evaluation.safety_status.value in {"stop", "caution"}:
        return GateValue.DENY
    if current_evaluation.safety_status.value == "unknown":
        return GateValue.UNKNOWN
    if (
        current_evaluation.safety_status.value == "clear"
        and current_evaluation.decision.value == "not_recommended"
    ):
        return GateValue.DENY
    if current_evaluation.eligible_for_recommendation:
        return GateValue.ALLOW
    return GateValue.UNKNOWN


def _participant_profile(
    request: RecommendationRequest,
    *,
    activity: str,
) -> str:
    if activity == Activity.SWIM.value and (
        any(age < MINOR_AGE_CUTOFF for age in request.party.ages)
        or request.party.participant_skill_level
        is ParticipantSkillLevel.BEGINNER
    ):
        return FAMILY_PROFILE
    return GENERAL_PROFILE


def _revalidate_condition_score(
    score: Any | None,
    *,
    spot: Any,
    activity: str,
    participant_profile: str,
    adult_supervision_confirmed: bool | None,
    participant_skill_level: ParticipantSkillLevel,
    at: datetime,
) -> IndexResult | None:
    if score is None or score.snapshot is None:
        return None
    if score.evaluated_at < at - MAX_CONDITION_AGE:
        return None
    try:
        activity_value = Activity(activity)
    except ValueError:
        return None
    metrics = tuple(
        metric
        for row in score.snapshot.metrics.all()
        if not (
            participant_profile == FAMILY_PROFILE
            and activity_value is Activity.SWIM
            and row.name == "adult_supervision_status"
        )
        if (metric := _database_metric(row)) is not None
    )
    if (
        participant_profile == FAMILY_PROFILE
        and activity_value is Activity.SWIM
        and adult_supervision_confirmed is not None
    ):
        metrics = (
            *metrics,
            Metric(
                name="adult_supervision_status",
                value=(
                    "confirmed"
                    if adult_supervision_confirmed
                    else "unavailable"
                ),
                unit="session_attestation",
                source="SESSION_CONTEXT",
                spatial_scope=f"recommendation-request:spot:{spot.pk}",
                observed_at=at,
                fetched_at=at,
                valid_from=at,
                valid_until=at,
                confidence=1.0,
            ),
        )
    try:
        context = EvaluationContext(
            activity=activity_value,
            at=at,
            environment=environment_for_spot(spot),
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level.value,
        )
    except ValueError:
        return None
    return evaluate_water_index(ObservationSet.from_metrics(*metrics), context)


def _database_metric(row: Any) -> Metric | None:
    if row.value is None:
        return None
    state = {
        "valid": MetricState.VALID,
        "conflict": MetricState.CONFLICT,
    }.get(row.state, MetricState.INVALID)
    try:
        return Metric(
            name=row.name,
            value=row.value,
            unit=row.unit,
            source=row.source,
            source_url=row.source_url,
            station_id=row.station_id,
            spatial_scope=row.spatial_scope,
            observed_at=row.observed_at,
            fetched_at=row.fetched_at,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            mode=MetricMode(row.mode),
            confidence=row.confidence,
            state=state,
        )
    except (TypeError, ValueError):
        return None


def _operation_gate(score: Any | None, *, activity: str, at: datetime) -> GateValue:
    if score is None or score.snapshot is None:
        return GateValue.UNKNOWN
    names = {
        "swim": ("official_entry_status", "access_status"),
        "surf": ("official_entry_status", "access_status"),
        "mudflat": ("official_entry_status", "access_status"),
        "onsen": ("facility_status",),
        "rafting": ("operator_status", "access_status"),
        "relax": ("access_status", "facility_status"),
    }.get(activity, ("access_status", "facility_status"))
    by_name = {metric.name: metric for metric in score.snapshot.metrics.all()}
    for name in names:
        metric = by_name.get(name)
        if metric is None or not _current_database_metric(metric, at=at):
            continue
        canonical = str(metric.value).strip().casefold().replace(" ", "_")
        if canonical in {
            "closed",
            "restricted",
            "suspended",
            "폐쇄",
            "통제",
            "입수통제",
            "휴업",
            "운휴",
        }:
            return GateValue.DENY
        if canonical in {
            "open",
            "allowed",
            "active",
            "operating",
            "clear",
            "개방",
            "허용",
            "운영",
            "영업",
            "정상",
        }:
            return GateValue.ALLOW
    return GateValue.UNKNOWN


def _current_database_metric(metric: Any, *, at: datetime) -> bool:
    normalized = _database_metric(metric)
    return bool(
        normalized is not None
        and normalized.confidence >= 0.8
        and normalized.is_current(
            at,
            max_age_seconds=SAFETY_MAX_AGE_SECONDS.get(normalized.name),
        )
    )


def _accessibility_gate(spot: Any) -> GateValue:
    state = getattr(spot, "accessibility_state", "unknown")
    if state == "verified":
        return GateValue.ALLOW
    if state == "unavailable":
        return GateValue.DENY
    return GateValue.UNKNOWN


def _pet_gate(spot: Any) -> GateValue:
    policy = getattr(spot, "pet_policy", "unknown")
    if policy == "allowed":
        return GateValue.ALLOW
    if policy == "not_allowed":
        return GateValue.DENY
    return GateValue.UNKNOWN


def _age_policy(spot: Any) -> AgePolicy:
    known = bool(getattr(spot, "age_policy_known", False))
    minimum = getattr(spot, "minimum_age", None)
    maximum = getattr(spot, "maximum_age", None)
    if not known or minimum is None:
        return AgePolicy(known=False)
    return AgePolicy(known=True, minimum_age=int(minimum), maximum_age=maximum)


def _evidence_confidence(spot: Any, evaluation: IndexResult | None) -> float:
    try:
        catalog = float(getattr(spot, "catalog_confidence", 0.0))
    except (TypeError, ValueError):
        catalog = 0.0
    catalog = max(0.0, min(1.0, catalog))
    if evaluation is None:
        return 0.0
    try:
        condition = float(evaluation.confidence)
    except (TypeError, ValueError):
        condition = 0.0
    return round(min(catalog, max(0.0, min(1.0, condition))), 6)


def _safe_tags(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(tag for tag in raw if isinstance(tag, str) and tag.strip())


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("recommendation time must be timezone-aware")
