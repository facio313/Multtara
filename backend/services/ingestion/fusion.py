"""Fuse current provider observations into one auditable Water Index input.

Fusion is intentionally conservative: demo rows are never promoted to live
evidence, provider authority is metric-specific, and unapproved sources cannot
clear a safety-critical gate. The Water Index remains the sole decision layer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Iterable

from services.water_index import (
    Activity,
    Environment,
    EvaluationContext,
    IndexResult,
    Metric,
    MetricMode,
    MetricState,
    ObservationSet,
    SAFETY_MAX_AGE_SECONDS,
    evaluation_valid_until,
    evaluate_water_index,
    safety_evidence_valid_until,
    supports_activity_environment,
)

from .persistence import MetricLineageInput, PersistenceResult, persist_evaluation
from .participant_profiles import canonical_participant_profile


FUSION_PROVIDER = "PONGDANG_FUSION"
FUSION_VERSION = "observation-fusion-v3"
_TIDE_WINDOW_START_METRIC = "official_tide_window_start"
_TIDE_WINDOW_END_METRIC = "official_tide_window_end"


_DEFAULT_SOURCE_PRIORITY = {
    "LOCAL_AUTHORITY": 100,
    "OFFICIAL_LOCAL": 100,
    "KMA_WARNING": 100,
    "KMA_LIGHTNING": 100,
    "MOE": 95,
    "KHOA": 90,
    "KMA": 80,
    "FACILITY_OPERATOR": 75,
    "TOUR_API": 50,
    "USER_REPORTED": 10,
}

_METRIC_SOURCE_PRIORITY = {
    "official_activity_grade": {"KHOA": 110},
    "official_activity_score": {"KHOA": 110},
    "rip_current_risk": {"KHOA": 110},
    "water_temperature_c": {"KHOA": 110, "MOE": 100, "KMA": 70},
    "wave_height_m": {"KHOA": 110, "KMA": 80},
    "maximum_wave_height_m": {"KHOA": 110, "KMA": 80},
    "air_temperature_c": {"KMA": 110, "KHOA": 90},
    "wind_speed_ms": {"KMA": 105, "KHOA": 100},
    "maximum_wind_speed_ms": {"KHOA": 105, "KMA": 100},
    "water_quality_status": {"MOE": 110, "LOCAL_AUTHORITY": 110},
    "weather_alert_level": {"KMA_WARNING": 110, "LOCAL_AUTHORITY": 110},
    "marine_hazard_status": {
        "KMA_WARNING": 110,
        "KHOA": 105,
        "LOCAL_AUTHORITY": 110,
    },
}

_SAFETY_SOURCE_ALLOWLIST: dict[str, frozenset[str]] = {
    "official_activity_grade": frozenset({"KHOA"}),
    "official_activity_score": frozenset({"KHOA"}),
    "official_stop_signal": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "KMA_WARNING", "KHOA"}
    ),
    "access_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR", "KHOA"}
    ),
    "official_entry_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "KHOA"}
    ),
    "patrol_status": frozenset({"LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}),
    "designated_swim_zone_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    # Supervision is party/session context. A globally stored provider row must
    # never claim it on a user's behalf.
    "adult_supervision_status": frozenset({"SESSION_CONTEXT"}),
    "facility_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR"}
    ),
    "operator_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR"}
    ),
    "weather_alert_level": frozenset({"KMA_WARNING", "LOCAL_AUTHORITY"}),
    "lightning_clearance_minutes": frozenset(
        {"KMA_LIGHTNING", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    "rip_current_risk": frozenset({"KHOA"}),
    "water_quality_status": frozenset(
        {"MOE", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    "water_temperature_c": frozenset(
        {
            "KHOA",
            "MOE",
            "LOCAL_AUTHORITY",
            "OFFICIAL_LOCAL",
            "FACILITY_OPERATOR",
        }
    ),
    "river_risk_level": frozenset(
        {"MOE", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    _TIDE_WINDOW_START_METRIC: frozenset({"KHOA"}),
    _TIDE_WINDOW_END_METRIC: frozenset({"KHOA"}),
    "tide_window_open": frozenset({"KHOA", "LOCAL_AUTHORITY"}),
    "marine_hazard_status": frozenset(
        {"KMA_WARNING", "KHOA", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    "fog_status": frozenset({"KMA_WARNING", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}),
    "designated_route_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
    "facility_hygiene_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR"}
    ),
    "hot_tub_temperature_c": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR"}
    ),
    "safety_equipment_status": frozenset(
        {"LOCAL_AUTHORITY", "OFFICIAL_LOCAL", "FACILITY_OPERATOR"}
    ),
    "upstream_rain_risk": frozenset(
        {"MOE", "KMA_WARNING", "LOCAL_AUTHORITY", "OFFICIAL_LOCAL"}
    ),
}


@dataclass(frozen=True, slots=True)
class MetricCandidate:
    database_id: int
    snapshot_id: int
    provider: str
    metric: Metric
    source_metric_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MetricSelection:
    candidate: MetricCandidate
    lineage: tuple[MetricLineageInput, ...]


@dataclass(frozen=True, slots=True)
class FusedObservation:
    provider: str
    provider_record_id: str
    ingestion_version: str
    state: str
    source_observed_at: datetime | None
    fetched_at: datetime
    valid_from: datetime
    valid_until: datetime
    evaluation_at: datetime
    spatial_scope: str
    source_url: str
    observations: ObservationSet
    source_metric_ids: tuple[int, ...]
    metric_lineage: tuple[MetricLineageInput, ...]


@dataclass(frozen=True, slots=True)
class FusionEvaluation:
    observation: FusedObservation
    result: IndexResult
    persistence: PersistenceResult | None


def fuse_spot_observations(
    *,
    spot: Any,
    at: datetime,
    fetched_at: datetime,
) -> FusedObservation:
    """Load real snapshots for ``spot`` and select one current metric per name."""

    _require_aware(at, "at")
    _require_aware(fetched_at, "fetched_at")
    from apps.conditions.models import ObservationMetric, ObservationSnapshot

    rows = (
        ObservationMetric.objects.select_related("snapshot")
        .filter(snapshot__spot=spot)
        .filter(snapshot__state__in=("live", "stale"))
        .exclude(snapshot__provider=FUSION_PROVIDER)
        .exclude(snapshot__state=ObservationSnapshot.SourceState.DEMO)
        .order_by("name", "id")
    )
    candidates = tuple(
        candidate
        for row in rows
        if (candidate := _candidate_from_model(row, at=at)) is not None
    )
    return fuse_candidates(
        candidates,
        at=at,
        fetched_at=fetched_at,
        spatial_scope=f"spot:{getattr(spot, 'pk', 'unknown')}",
    )


def fuse_candidates(
    candidates: Iterable[MetricCandidate],
    *,
    at: datetime,
    fetched_at: datetime,
    spatial_scope: str,
) -> FusedObservation:
    """Pure selection core, separated from the ORM for boundary testing."""

    _require_aware(at, "at")
    _require_aware(fetched_at, "fetched_at")
    grouped: dict[str, list[MetricCandidate]] = {}
    contextualized = _contextualize_tide_window_candidates(tuple(candidates), at=at)
    for candidate in contextualized:
        source = _canonical_source(candidate.metric.source)
        allowed = _SAFETY_SOURCE_ALLOWLIST.get(candidate.metric.name)
        if allowed is not None:
            if source not in allowed:
                continue
            if _canonical_source(candidate.provider) != source:
                continue
        if not _temporally_applicable(candidate.metric, at=at):
            continue
        grouped.setdefault(candidate.metric.name, []).append(candidate)

    selected: list[MetricSelection] = []
    for name, values in sorted(grouped.items()):
        selected.append(_select_candidate(name, values))

    metrics = tuple(item.candidate.metric for item in selected)
    lineage = tuple(
        edge
        for item in selected
        for edge in item.lineage
    )
    ids = tuple(sorted({edge.source_metric_id for edge in lineage}))
    observed_at = max((metric.observed_at for metric in metrics), default=None)
    state = "live" if metrics else "missing"
    record_payload = {
        "at": at.isoformat(),
        "metric_ids": ids,
        "lineage": [
            (
                edge.derived_metric_name,
                edge.source_metric_id,
                edge.relation,
                edge.priority,
            )
            for edge in lineage
        ],
        "states": [metric.state.value for metric in metrics],
        "version": FUSION_VERSION,
    }
    provider_record_id = hashlib.sha256(
        json.dumps(record_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return FusedObservation(
        provider=FUSION_PROVIDER,
        provider_record_id=provider_record_id,
        ingestion_version=FUSION_VERSION,
        state=state,
        source_observed_at=observed_at,
        fetched_at=fetched_at,
        valid_from=at,
        valid_until=at,
        evaluation_at=at,
        spatial_scope=spatial_scope,
        source_url="",
        observations=ObservationSet.from_metrics(*metrics),
        source_metric_ids=ids,
        metric_lineage=lineage,
    )


def evaluate_fused_spot(
    *,
    spot: Any,
    activity: Activity,
    at: datetime,
    fetched_at: datetime,
    participant_profile: str = "general",
    dry_run: bool = False,
) -> FusionEvaluation:
    participant_profile = canonical_participant_profile(participant_profile)
    observation = fuse_spot_observations(spot=spot, at=at, fetched_at=fetched_at)
    context = EvaluationContext(
        activity=activity,
        at=at,
        environment=environment_for_spot(spot),
        participant_profile=participant_profile,
    )
    result = evaluate_water_index(
        observation.observations,
        context,
    )
    observation = _contextualize_observation(
        observation,
        context=context,
    )
    persistence = None
    if not dry_run:
        persistence = persist_evaluation(
            spot=spot,
            observation=observation,
            result=result,
            participant_profile=participant_profile,
        )
    return FusionEvaluation(
        observation=observation,
        result=result,
        persistence=persistence,
    )


def environment_for_spot(spot: Any) -> Environment:
    return environment_for_spot_type(getattr(spot, "type", ""))


def environment_for_spot_type(value: Any) -> Environment:
    spot_type = str(value).strip().lower()
    if spot_type in {"beach", "sea", "marine_beach", "coastal_road"}:
        return Environment.MARINE_BEACH
    if spot_type in {"river", "valley", "lake", "riverside", "reservoir"}:
        return Environment.INLAND_WATER
    if spot_type in {"mudflat", "tidal_flat"}:
        return Environment.TIDAL_FLAT
    if spot_type in {"hotspring", "pool", "waterpark", "licensed_facility"}:
        return Environment.LICENSED_FACILITY
    return Environment.WATERSIDE


def activity_supported_for_spot(spot: Any, activity: Activity) -> bool:
    return supports_activity_environment(activity, environment_for_spot(spot))


def _candidate_from_model(row: Any, *, at: datetime) -> MetricCandidate | None:
    state = {
        "valid": MetricState.VALID,
        "conflict": MetricState.CONFLICT,
    }.get(row.state, MetricState.INVALID)
    if row.value is None:
        return None
    try:
        metric = Metric(
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
    return MetricCandidate(
        database_id=row.pk,
        snapshot_id=row.snapshot_id,
        provider=row.snapshot.provider,
        metric=metric,
        source_metric_ids=(row.pk,),
    )


def _contextualize_tide_window_candidates(
    candidates: tuple[MetricCandidate, ...],
    *,
    at: datetime,
) -> tuple[MetricCandidate, ...]:
    """Derive the current tide gate only from an explicit official window."""

    boundaries: dict[int, dict[str, MetricCandidate]] = {}
    for candidate in candidates:
        if candidate.metric.name not in {
            _TIDE_WINDOW_START_METRIC,
            _TIDE_WINDOW_END_METRIC,
        }:
            continue
        if (
            _canonical_source(candidate.provider) != "KHOA"
            or _canonical_source(candidate.metric.source) != "KHOA"
        ):
            continue
        boundaries.setdefault(candidate.snapshot_id, {})[
            candidate.metric.name
        ] = candidate

    derived_by_snapshot: dict[int, MetricCandidate] = {}
    for snapshot_id, pair in boundaries.items():
        start = pair.get(_TIDE_WINDOW_START_METRIC)
        end = pair.get(_TIDE_WINDOW_END_METRIC)
        if start is None or end is None:
            continue
        derived = _tide_candidate_from_boundaries(start, end, at=at)
        if derived is not None:
            derived_by_snapshot[snapshot_id] = derived

    contextualized: list[MetricCandidate] = []
    for candidate in candidates:
        if candidate.metric.name in {
            _TIDE_WINDOW_START_METRIC,
            _TIDE_WINDOW_END_METRIC,
        }:
            # Boundary metrics remain on their original provider snapshot. The
            # fused boolean links back to them explicitly instead of copying
            # datetime strings into the Water Index input.
            continue
        if (
            candidate.metric.name == "tide_window_open"
            and _canonical_source(candidate.provider) == "KHOA"
            and _canonical_source(candidate.metric.source) == "KHOA"
        ):
            if candidate.snapshot_id in derived_by_snapshot:
                continue
            legacy = _tide_candidate_from_legacy_status(candidate, at=at)
            if legacy is not None:
                contextualized.append(legacy)
            continue
        contextualized.append(candidate)
    contextualized.extend(derived_by_snapshot.values())
    return tuple(contextualized)


def _tide_candidate_from_boundaries(
    start_candidate: MetricCandidate,
    end_candidate: MetricCandidate,
    *,
    at: datetime,
) -> MetricCandidate | None:
    start = _official_datetime(start_candidate.metric.value)
    end = _official_datetime(end_candidate.metric.value)
    if start is None or end is None or end <= start:
        return None
    for candidate in (start_candidate, end_candidate):
        metric = candidate.metric
        if (
            candidate.snapshot_id != start_candidate.snapshot_id
            or metric.valid_from != start
            or metric.valid_until != end
            or metric.fetched_at > at
            or metric.spatial_scope != start_candidate.metric.spatial_scope
            or metric.source_url != start_candidate.metric.source_url
        ):
            return None
    return _derived_tide_candidate(
        template=start_candidate,
        source_metric_ids=(
            *start_candidate.source_metric_ids,
            *end_candidate.source_metric_ids,
        ),
        start=start,
        end=end,
        at=at,
        confidence=min(
            start_candidate.metric.confidence,
            end_candidate.metric.confidence,
        ),
        observed_at=max(
            start_candidate.metric.observed_at,
            end_candidate.metric.observed_at,
        ),
        fetched_at=max(
            start_candidate.metric.fetched_at,
            end_candidate.metric.fetched_at,
        ),
    )


def _tide_candidate_from_legacy_status(
    candidate: MetricCandidate,
    *,
    at: datetime,
) -> MetricCandidate | None:
    metric = candidate.metric
    start = metric.valid_from
    end = metric.valid_until
    if start is None or end is None or end <= start or metric.fetched_at > at:
        return None
    return _derived_tide_candidate(
        template=candidate,
        source_metric_ids=candidate.source_metric_ids,
        start=start,
        end=end,
        at=at,
        confidence=metric.confidence,
        observed_at=metric.observed_at,
        fetched_at=metric.fetched_at,
    )


def _derived_tide_candidate(
    *,
    template: MetricCandidate,
    source_metric_ids: tuple[int, ...],
    start: datetime,
    end: datetime,
    at: datetime,
    confidence: float,
    observed_at: datetime,
    fetched_at: datetime,
) -> MetricCandidate | None:
    local_date = at.astimezone(start.tzinfo).date()
    if not start.date() <= local_date <= end.date():
        return None
    is_open = start <= at <= end
    valid_from = start if is_open else at
    valid_until = end if is_open else at
    metric = Metric(
        name="tide_window_open",
        value=is_open,
        unit="boolean",
        source="KHOA",
        source_url=template.metric.source_url,
        station_id=template.metric.station_id,
        spatial_scope=template.metric.spatial_scope,
        observed_at=observed_at,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        mode=MetricMode.FORECAST,
        confidence=confidence,
        state=MetricState.VALID,
    )
    return MetricCandidate(
        database_id=min(source_metric_ids),
        snapshot_id=template.snapshot_id,
        provider=template.provider,
        metric=metric,
        source_metric_ids=tuple(sorted(set(source_metric_ids))),
    )


def _official_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _temporally_applicable(metric: Metric, *, at: datetime) -> bool:
    if metric.mode is not MetricMode.FORECAST and metric.observed_at > at:
        return False
    if metric.valid_from is not None and at < metric.valid_from:
        return False
    if metric.name in SAFETY_MAX_AGE_SECONDS:
        effective_expiry = safety_evidence_valid_until(metric)
        if effective_expiry is None or at > effective_expiry:
            return False
    elif metric.valid_until is not None and at > metric.valid_until:
        return False
    return True


def _select_candidate(name: str, values: list[MetricCandidate]) -> MetricSelection:
    ranked = sorted(
        values,
        key=lambda item: (
            _source_priority(name, item.metric.source),
            item.metric.observed_at,
            item.metric.fetched_at,
            item.database_id,
        ),
        reverse=True,
    )
    winner = ranked[0]
    newest_by_source: dict[str, MetricCandidate] = {}
    for candidate in ranked:
        if (
            name not in _SAFETY_SOURCE_ALLOWLIST
            and _source_priority(name, candidate.metric.source)
            != _source_priority(name, winner.metric.source)
        ):
            continue
        newest_by_source.setdefault(_canonical_source(candidate.metric.source), candidate)
    peers = tuple(newest_by_source.values())
    conflicting = tuple(
        peer
        for peer in peers[1:]
        if not _equivalent_value(winner.metric.value, peer.metric.value)
    )
    if conflicting:
        conflicted_winner = replace(
            winner,
            metric=replace(
                winner.metric,
                state=MetricState.CONFLICT,
                confidence=min(peer.metric.confidence for peer in peers),
            ),
        )
        return MetricSelection(
            candidate=conflicted_winner,
            lineage=(
                *_lineage_for(winner, relation="selected"),
                *(
                    edge
                    for peer in conflicting
                    for edge in _lineage_for(peer, relation="conflict")
                ),
            ),
        )
    return MetricSelection(
        candidate=winner,
        lineage=_lineage_for(winner, relation="selected"),
    )


def _lineage_for(
    candidate: MetricCandidate,
    *,
    relation: str,
) -> tuple[MetricLineageInput, ...]:
    return tuple(
        MetricLineageInput(
            derived_metric_name=candidate.metric.name,
            source_metric_id=source_metric_id,
            relation=relation,
            priority=_source_priority(candidate.metric.name, candidate.metric.source),
        )
        for source_metric_id in sorted(set(candidate.source_metric_ids))
    )


def _contextualize_observation(
    observation: FusedObservation,
    *,
    context: EvaluationContext,
) -> FusedObservation:
    valid_until = evaluation_valid_until(observation.observations, context)
    record_payload = {
        "activity": context.activity.value,
        "at": context.at.isoformat(),
        "metric_ids": observation.source_metric_ids,
        "participant_profile": context.participant_profile,
        "states": [
            metric.state.value
            for metric in observation.observations.metrics.values()
        ],
        "valid_until": valid_until.isoformat(),
        "version": FUSION_VERSION,
    }
    provider_record_id = hashlib.sha256(
        json.dumps(record_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return replace(
        observation,
        provider_record_id=provider_record_id,
        valid_until=valid_until,
    )


def _source_priority(name: str, source: str) -> int:
    canonical = _canonical_source(source)
    return _METRIC_SOURCE_PRIORITY.get(name, {}).get(
        canonical,
        _DEFAULT_SOURCE_PRIORITY.get(canonical, 0),
    )


def _canonical_source(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _equivalent_value(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-9
    return str(left).strip().casefold() == str(right).strip().casefold()


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
