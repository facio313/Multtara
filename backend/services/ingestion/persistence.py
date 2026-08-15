"""Transactional persistence for normalized observations and index results.

The conditions models are imported inside the public function so this service
can be imported while migrations are being generated, and so the provider and
adapter test suites do not require Django application setup.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from django.db import transaction

from services.water_index import IndexResult, Metric

from .participant_profiles import canonical_participant_profile


class NormalizedObservation(Protocol):
    """Structural contract shared by every provider adapter.

    Provider-specific adapters intentionally remain independent. Persistence
    accepts only their normalized, credential-free public projection.
    """

    provider: str
    provider_record_id: str
    ingestion_version: str
    state: str
    source_observed_at: datetime | None
    fetched_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    spatial_scope: str
    source_url: str
    observations: Any


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    snapshot_id: int
    score_id: int
    snapshot_created: bool
    score_created: bool


@dataclass(frozen=True, slots=True)
class SnapshotPersistenceResult:
    snapshot_id: int
    snapshot_created: bool


@dataclass(frozen=True, slots=True)
class MetricLineageInput:
    derived_metric_name: str
    source_metric_id: int
    relation: str
    priority: int


def _upsert_snapshot(*, spot: Any, observation: NormalizedObservation) -> tuple[Any, bool]:
    (
        ObservationSnapshot,
        ObservationMetric,
        ObservationMetricLineage,
        _,
    ) = _condition_models()
    snapshot, snapshot_created = ObservationSnapshot.objects.update_or_create(
        spot=spot,
        provider=observation.provider,
        provider_record_id=observation.provider_record_id,
        ingestion_version=observation.ingestion_version,
        defaults={
            "state": observation.state,
            "observed_at": observation.source_observed_at,
            "fetched_at": observation.fetched_at,
            "valid_from": observation.valid_from,
            "valid_until": observation.valid_until,
            "spatial_scope": observation.spatial_scope,
            "source_url": observation.source_url,
        },
    )

    metrics_by_name: dict[str, Any] = {}
    for metric in observation.observations.metrics.values():
        persisted_metric, _ = ObservationMetric.objects.update_or_create(
            snapshot=snapshot,
            name=metric.name,
            defaults=_metric_defaults(metric),
        )
        metrics_by_name[metric.name] = persisted_metric
    stale_metrics = snapshot.metrics.exclude(name__in=metrics_by_name)
    if stale_metrics.exists():
        stale_metrics.delete()
    _sync_metric_lineage(
        spot=spot,
        snapshot=snapshot,
        metrics_by_name=metrics_by_name,
        lineage_model=ObservationMetricLineage,
        metric_model=ObservationMetric,
        inputs=tuple(getattr(observation, "metric_lineage", ())),
    )
    return snapshot, snapshot_created


def _sync_metric_lineage(
    *,
    spot: Any,
    snapshot: Any,
    metrics_by_name: dict[str, Any],
    lineage_model: Any,
    metric_model: Any,
    inputs: tuple[MetricLineageInput, ...],
) -> None:
    source_ids = {item.source_metric_id for item in inputs}
    sources = metric_model.objects.select_related("snapshot").in_bulk(source_ids)
    if set(sources) != source_ids:
        raise ValueError("Fused metric lineage references a missing source metric")

    retained_lineage_ids: list[int] = []
    for item in inputs:
        derived_metric = metrics_by_name.get(item.derived_metric_name)
        source_metric = sources.get(item.source_metric_id)
        if derived_metric is None or source_metric is None:
            raise ValueError("Fused metric lineage does not match a persisted metric")
        if item.relation not in {"selected", "conflict"}:
            raise ValueError("Fused metric lineage relation is invalid")
        if (
            isinstance(item.priority, bool)
            or not isinstance(item.priority, int)
            or not 0 <= item.priority <= 65_535
        ):
            raise ValueError("Fused metric lineage priority is invalid")
        if source_metric.snapshot.spot_id != getattr(spot, "pk", None):
            raise ValueError("Fused metric lineage crosses WaterSpot boundaries")
        if source_metric.snapshot.provider == "PONGDANG_FUSION":
            raise ValueError("Fused metric lineage must reference original evidence")
        lineage, _ = lineage_model.objects.update_or_create(
            derived_metric=derived_metric,
            source_metric=source_metric,
            defaults={
                "relation": item.relation,
                "priority": item.priority,
            },
        )
        retained_lineage_ids.append(lineage.pk)

    stale_lineage = lineage_model.objects.filter(
        derived_metric__snapshot=snapshot
    ).exclude(pk__in=retained_lineage_ids)
    if stale_lineage.exists():
        stale_lineage.delete()


@transaction.atomic
def persist_observation(
    *, spot: Any, observation: NormalizedObservation
) -> SnapshotPersistenceResult:
    """Persist a normalized provider snapshot without inventing an activity score."""

    snapshot, snapshot_created = _upsert_snapshot(
        spot=spot,
        observation=observation,
    )
    return SnapshotPersistenceResult(
        snapshot_id=snapshot.pk,
        snapshot_created=snapshot_created,
    )


@transaction.atomic
def persist_evaluation(
    *,
    spot: Any,
    observation: NormalizedObservation,
    result: IndexResult,
    participant_profile: str = "general",
) -> PersistenceResult:
    """Upsert one source record, its metrics, and its evaluated score atomically.

    ``provider_record_id`` is a stable hash of the typed provider record. The
    model's unique constraint on spot/provider/record/version makes identical
    retries idempotent while a revised upstream record creates a new auditable
    snapshot.
    """

    ObservationSnapshot, _, _, ConditionScore = _condition_models()
    snapshot, snapshot_created = _upsert_snapshot(
        spot=spot,
        observation=observation,
    )

    profile = canonical_participant_profile(participant_profile)
    score_defaults = _score_defaults(result)
    # Locking the parent snapshot serializes repeated writes for this stable
    # provider record even though legacy ConditionScore has no unique key.
    ObservationSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    existing_score = (
        ConditionScore.objects.select_for_update()
        .filter(
            snapshot=snapshot,
            activity=result.activity.value,
            participant_profile=profile,
            methodology_version=result.methodology_version,
        )
        .order_by("pk")
        .first()
    )
    if existing_score is None:
        score = ConditionScore.objects.create(
            snapshot=snapshot,
            spot=spot,
            activity=result.activity.value,
            participant_profile=profile,
            **score_defaults,
        )
        score_created = True
    else:
        score = existing_score
        for field_name, value in score_defaults.items():
            setattr(score, field_name, value)
        score.spot = spot
        score.save(update_fields=["spot", *score_defaults.keys()])
        score_created = False

    return PersistenceResult(
        snapshot_id=snapshot.pk,
        score_id=score.pk,
        snapshot_created=snapshot_created,
        score_created=score_created,
    )


def _condition_models() -> tuple[Any, Any, Any, Any]:
    from apps.conditions.models import (  # imported lazily by design
        ConditionScore,
        ObservationMetric,
        ObservationMetricLineage,
        ObservationSnapshot,
    )

    return (
        ObservationSnapshot,
        ObservationMetric,
        ObservationMetricLineage,
        ConditionScore,
    )


def _metric_defaults(metric: Metric) -> dict[str, Any]:
    value_type, value_fields = _metric_value_fields(metric.value)
    return {
        "value_type": value_type,
        **value_fields,
        "unit": metric.unit,
        "mode": metric.mode.value,
        "state": metric.state.value,
        "confidence": metric.confidence,
        "source": metric.source,
        "source_url": metric.source_url,
        "station_id": metric.station_id,
        "spatial_scope": metric.spatial_scope,
        "observed_at": metric.observed_at,
        "fetched_at": metric.fetched_at,
        "valid_from": metric.valid_from,
        "valid_until": metric.valid_until,
    }


def _metric_value_fields(value: Any) -> tuple[str, dict[str, Any]]:
    blank = {
        "numeric_value": None,
        "text_value": None,
        "boolean_value": None,
    }
    if isinstance(value, bool):
        blank["boolean_value"] = value
        return "boolean", blank
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        blank["numeric_value"] = float(value)
        return "number", blank
    blank["text_value"] = str(value)
    return "text", blank


def _score_defaults(result: IndexResult) -> dict[str, Any]:
    return {
        "score": result.score,
        "safety_status": result.safety_status.value,
        "decision": result.decision.value,
        "confidence": result.confidence,
        "coverage": result.coverage,
        "score_range": list(result.score_range) if result.score_range is not None else [],
        "gates": [_json_value(asdict(gate)) for gate in result.gates],
        "contributions": [
            _json_value(asdict(contribution)) for contribution in result.contributions
        ],
        "missing_metrics": list(result.missing_metrics),
        "stale_or_conflicting_metrics": list(result.stale_or_conflicting_metrics),
        "limitations": list(result.limitations),
        "methodology_version": result.methodology_version,
        "evaluated_at": result.evaluated_at,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
