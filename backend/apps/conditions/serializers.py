from dataclasses import dataclass
from datetime import timedelta

from rest_framework import serializers

from services.ingestion.fusion import environment_for_spot
from services.public_urls import public_https_url
from services.water_index import (
    Activity,
    EvaluationContext,
    Metric,
    MetricMode,
    MetricState,
    MINIMUM_SAFETY_INPUT_CONFIDENCE,
    SAFETY_MAX_AGE_SECONDS,
    SURF_GRADE_DETAIL_MISSING,
    SURF_OFFICIAL_GRADE_MISSING,
    SURF_SKILL_LEVEL_REQUIRED,
    assess_surf_skill_evidence,
    required_safety_metric_groups,
)

from .models import (
    ConditionScore,
    ObservationMetric,
    ObservationSnapshot,
    WaterCondition,
)

_SENSITIVE_AUDIT_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "headers",
        "raw_payload",
        "request",
        "response",
        "service_key",
        "servicekey",
    }
)


def _public_audit_value(value):
    """Recursively remove transport internals from structured audit reasons."""

    if isinstance(value, list):
        return [_public_audit_value(item) for item in value]
    if isinstance(value, dict):
        public = {}
        for key, item in value.items():
            canonical_key = str(key).strip().lower()
            if canonical_key in _SENSITIVE_AUDIT_KEYS:
                continue
            if canonical_key == "source_url":
                public[key] = public_https_url(item)
            else:
                public[key] = _public_audit_value(item)
        return public
    return value


class WaterConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterCondition
        fields = "__all__"


class ObservationMetricSerializer(serializers.ModelSerializer):
    value = serializers.ReadOnlyField()
    provenance = serializers.SerializerMethodField()
    lineage = serializers.SerializerMethodField()

    class Meta:
        model = ObservationMetric
        fields = (
            "id",
            "name",
            "value_type",
            "value",
            "unit",
            "mode",
            "state",
            "confidence",
            "provenance",
            "lineage",
        )
        read_only_fields = fields

    def get_provenance(self, metric: ObservationMetric) -> dict:
        return {
            "provider": metric.snapshot.provider,
            "provider_record_id": metric.snapshot.provider_record_id,
            "source": metric.source,
            "source_url": public_https_url(metric.source_url),
            "station_id": metric.station_id,
            "spatial_scope": metric.spatial_scope,
            "observed_at": metric.observed_at,
            "fetched_at": metric.fetched_at,
            "valid_from": metric.valid_from,
            "valid_until": metric.valid_until,
        }

    def get_lineage(self, metric: ObservationMetric) -> list[dict]:
        return [
            {
                "relation": edge.relation,
                "priority": edge.priority,
                "source_metric_id": edge.source_metric_id,
                "source_metric_name": edge.source_metric.name,
                "provider": edge.source_metric.snapshot.provider,
                "source": edge.source_metric.source,
                "state": edge.source_metric.state,
                "source_url": public_https_url(edge.source_metric.source_url),
                "spatial_scope": edge.source_metric.spatial_scope,
                "observed_at": edge.source_metric.observed_at,
                "fetched_at": edge.source_metric.fetched_at,
                "valid_from": edge.source_metric.valid_from,
                "valid_until": edge.source_metric.valid_until,
            }
            for edge in metric.lineage_sources.all()
        ]


class ObservationSnapshotSerializer(serializers.ModelSerializer):
    spot_name = serializers.CharField(source="spot.name", read_only=True)
    metrics = ObservationMetricSerializer(many=True, read_only=True)
    provenance = serializers.SerializerMethodField()

    class Meta:
        model = ObservationSnapshot
        fields = (
            "id",
            "spot",
            "spot_name",
            "provider",
            "provider_record_id",
            "state",
            "observed_at",
            "fetched_at",
            "valid_from",
            "valid_until",
            "spatial_scope",
            "ingestion_version",
            "created_at",
            "provenance",
            "metrics",
        )
        read_only_fields = fields

    def get_provenance(self, snapshot: ObservationSnapshot) -> dict:
        return {
            "provider": snapshot.provider,
            "provider_record_id": snapshot.provider_record_id,
            "source_url": public_https_url(snapshot.source_url),
            "spatial_scope": snapshot.spatial_scope,
            "observed_at": snapshot.observed_at,
            "fetched_at": snapshot.fetched_at,
            "valid_from": snapshot.valid_from,
            "valid_until": snapshot.valid_until,
            "ingestion_version": snapshot.ingestion_version,
        }


class ConditionScoreSerializer(serializers.ModelSerializer):
    spot_name = serializers.CharField(source="spot.name", read_only=True)
    score = serializers.SerializerMethodField()
    suitability_score = serializers.SerializerMethodField()
    safety_status = serializers.SerializerMethodField()
    decision = serializers.SerializerMethodField()
    score_range = serializers.SerializerMethodField()
    snapshot = ObservationSnapshotSerializer(read_only=True)
    gates = serializers.SerializerMethodField()
    contributions = serializers.SerializerMethodField()
    missing_metrics = serializers.SerializerMethodField()
    stale_or_conflicting_metrics = serializers.SerializerMethodField()

    class Meta:
        model = ConditionScore
        fields = (
            "id",
            "spot",
            "spot_name",
            "snapshot",
            "activity",
            "participant_profile",
            "participant_skill_level",
            "score",
            "suitability_score",
            "safety_status",
            "decision",
            "confidence",
            "coverage",
            "score_range",
            "gates",
            "contributions",
            "missing_metrics",
            "stale_or_conflicting_metrics",
            "limitations",
            "methodology_version",
            "evaluated_at",
            "computed_at",
        )
        read_only_fields = fields

    def get_gates(self, score: ConditionScore) -> list:
        current_failures = self._effective_failures(score)
        effective_gates = [
            {
                "rule_id": (
                    "suitability.surf.skill_grade"
                    if failure.reason_code.startswith("SURF_")
                    else "safety.evidence.current"
                ),
                "severity": "unknown",
                "metric_name": failure.metric_name,
                "reason_code": failure.reason_code,
            }
            for failure in current_failures
        ]
        return [*effective_gates, *_public_audit_value(score.gates)]

    def get_contributions(self, score: ConditionScore) -> list:
        return _public_audit_value(score.contributions)

    def get_missing_metrics(self, score: ConditionScore) -> list:
        effective_missing = [
            failure.metric_name
            for failure in self._effective_failures(score)
            if failure.category == "missing"
        ]
        return list(dict.fromkeys([*score.missing_metrics, *effective_missing]))

    def get_stale_or_conflicting_metrics(self, score: ConditionScore) -> list:
        effective_stale = [
            failure.metric_name
            for failure in self._effective_failures(score)
            if failure.category == "stale"
        ]
        return list(
            dict.fromkeys(
                [*score.stale_or_conflicting_metrics, *effective_stale]
            )
        )

    def get_safety_status(self, score: ConditionScore) -> str:
        if self._is_effectively_unknown(score):
            return ConditionScore.SafetyStatus.UNKNOWN.value
        return score.safety_status

    def get_decision(self, score: ConditionScore) -> str:
        if self._is_effectively_unknown(score):
            return ConditionScore.Decision.UNKNOWN.value
        return score.decision

    def get_score_range(self, score: ConditionScore) -> list:
        if self._is_effectively_unknown(score) or score.score is None:
            return []
        return score.score_range

    def get_score(self, score: ConditionScore) -> float | None:
        if self._is_effectively_unknown(score) or score.safety_status in {
            ConditionScore.SafetyStatus.STOP,
            ConditionScore.SafetyStatus.UNKNOWN,
        }:
            return None
        return score.score

    def get_suitability_score(self, score: ConditionScore) -> float | None:
        return self.get_score(score)

    def _is_effectively_unknown(self, score: ConditionScore) -> bool:
        """Project a stored decision through current evidence availability.

        Only the ``latest`` action supplies ``effective_as_of``.  Historical
        list/detail responses remain an immutable audit view of what was
        evaluated, while a current consumer can never receive an expired
        safety status or suitability score as if its evidence were still
        usable.
        """

        return bool(self._effective_failures(score))

    def _effective_failures(
        self,
        score: ConditionScore,
    ) -> tuple["_EffectiveEvidenceFailure", ...]:
        as_of = self.context.get("effective_as_of")
        if (
            as_of is None
            or score.safety_status == ConditionScore.SafetyStatus.UNKNOWN
        ):
            return ()

        cache = getattr(self, "_effective_failure_cache", None)
        if cache is None:
            cache = {}
            self._effective_failure_cache = cache
        cache_key = (score.pk, as_of)
        if cache_key not in cache:
            cache[cache_key] = _effective_evidence_failures(score, as_of=as_of)
        return cache[cache_key]


@dataclass(frozen=True, slots=True)
class _EffectiveEvidenceFailure:
    metric_name: str
    reason_code: str
    category: str


def _effective_evidence_failures(
    score: ConditionScore,
    *,
    as_of,
) -> tuple[_EffectiveEvidenceFailure, ...]:
    snapshot = score.snapshot
    if snapshot is None:
        return (
            _EffectiveEvidenceFailure(
                metric_name="evaluation_snapshot",
                reason_code="EVALUATION_SNAPSHOT_MISSING",
                category="missing",
            ),
        )
    if snapshot.valid_from is not None and as_of < snapshot.valid_from:
        return (
            _EffectiveEvidenceFailure(
                metric_name="evaluation_snapshot",
                reason_code="EVALUATION_SNAPSHOT_NOT_CURRENT",
                category="stale",
            ),
        )
    if snapshot.valid_until is not None and as_of > snapshot.valid_until:
        return (
            _EffectiveEvidenceFailure(
                metric_name="evaluation_snapshot",
                reason_code="EVALUATION_SNAPSHOT_EXPIRED",
                category="stale",
            ),
        )

    try:
        context = EvaluationContext(
            activity=Activity(score.activity),
            at=as_of,
            environment=environment_for_spot(score.spot),
            participant_profile=score.participant_profile,
            participant_skill_level=score.participant_skill_level,
        )
    except (TypeError, ValueError):
        return (
            _EffectiveEvidenceFailure(
                metric_name="activity",
                reason_code="WATER_INDEX_CONTRACT_UNAVAILABLE",
                category="missing",
            ),
        )

    metrics_by_name = {metric.name: metric for metric in snapshot.metrics.all()}
    failures = []
    for group in required_safety_metric_groups(context):
        present = tuple(
            metrics_by_name[name]
            for name in group
            if name in metrics_by_name
        )
        if any(
            _persisted_safety_metric_is_current(metric, as_of=as_of)
            for metric in present
        ):
            continue
        failures.append(
            _EffectiveEvidenceFailure(
                metric_name="|".join(group),
                reason_code=(
                    "REQUIRED_SAFETY_EVIDENCE_NOT_CURRENT"
                    if present
                    else "REQUIRED_SAFETY_EVIDENCE_MISSING"
                ),
                category="stale" if present else "missing",
            )
        )
    if context.activity is Activity.SURF:
        domain_metrics = tuple(
            converted
            for metric in metrics_by_name.values()
            if (converted := _persisted_domain_metric(metric)) is not None
        )
        assessment = assess_surf_skill_evidence(
            domain_metrics,
            participant_skill_level=score.participant_skill_level,
            at=as_of,
        )
        if not assessment.matched:
            missing_reasons = {
                SURF_SKILL_LEVEL_REQUIRED,
                SURF_OFFICIAL_GRADE_MISSING,
                SURF_GRADE_DETAIL_MISSING,
            }
            metric_name = {
                SURF_SKILL_LEVEL_REQUIRED: "participant_skill_level",
                SURF_OFFICIAL_GRADE_MISSING: "official_activity_grade",
                SURF_GRADE_DETAIL_MISSING: "official_grade_detail",
            }.get(assessment.reason_code, "official_grade_detail")
            failures.append(
                _EffectiveEvidenceFailure(
                    metric_name=metric_name,
                    reason_code=assessment.reason_code,
                    category=(
                        "missing"
                        if assessment.reason_code in missing_reasons
                        else "stale"
                    ),
                )
            )
    return tuple(failures)


def _persisted_domain_metric(metric: ObservationMetric) -> Metric | None:
    if metric.value is None:
        return None
    state = {
        ObservationMetric.State.VALID: MetricState.VALID,
        ObservationMetric.State.CONFLICT: MetricState.CONFLICT,
    }.get(metric.state, MetricState.INVALID)
    try:
        return Metric(
            name=metric.name,
            value=metric.value,
            unit=metric.unit,
            source=metric.source,
            source_url=metric.source_url,
            station_id=metric.station_id,
            spatial_scope=metric.spatial_scope,
            observed_at=metric.observed_at,
            fetched_at=metric.fetched_at,
            valid_from=metric.valid_from,
            valid_until=metric.valid_until,
            mode=MetricMode(metric.mode),
            confidence=metric.confidence,
            state=state,
        )
    except (TypeError, ValueError):
        return None


def _persisted_safety_metric_is_current(metric: ObservationMetric, *, as_of) -> bool:
    if (
        metric.state != ObservationMetric.State.VALID
        or metric.confidence < MINIMUM_SAFETY_INPUT_CONFIDENCE
    ):
        return False
    if (
        metric.mode != ObservationMetric.Mode.FORECAST
        and as_of < metric.observed_at
    ):
        return False
    if metric.valid_from is not None and as_of < metric.valid_from:
        return False

    expiries = []
    if metric.valid_until is not None:
        expiries.append(metric.valid_until)
    max_age_seconds = SAFETY_MAX_AGE_SECONDS.get(metric.name)
    if (
        max_age_seconds is not None
        and metric.mode != ObservationMetric.Mode.FORECAST
    ):
        expiries.append(
            metric.observed_at + timedelta(seconds=max_age_seconds)
        )
    return bool(expiries) and as_of <= min(expiries)
