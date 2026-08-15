from rest_framework import serializers

from services.public_urls import public_https_url

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
    snapshot = ObservationSnapshotSerializer(read_only=True)
    gates = serializers.SerializerMethodField()
    contributions = serializers.SerializerMethodField()

    class Meta:
        model = ConditionScore
        fields = (
            "id",
            "spot",
            "spot_name",
            "snapshot",
            "activity",
            "participant_profile",
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
        return _public_audit_value(score.gates)

    def get_contributions(self, score: ConditionScore) -> list:
        return _public_audit_value(score.contributions)

    def get_score(self, score: ConditionScore) -> float | None:
        if score.safety_status in {
            ConditionScore.SafetyStatus.STOP,
            ConditionScore.SafetyStatus.UNKNOWN,
        }:
            return None
        return score.score

    def get_suitability_score(self, score: ConditionScore) -> float | None:
        return self.get_score(score)
