"""Evidence collection and fail-closed daily Water Index projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from services.ingestion.fusion import (
    activity_supported_for_spot,
    environment_for_spot,
    fuse_spot_observations,
)
from services.ingestion.khoa_adapter import (
    AdaptedKhoaObservation,
    KhoaAdapterError,
    adapt_beach_forecast,
    adapt_mudflat_forecast,
    adapt_surf_forecast,
)
from services.ingestion.marine import match_observation_to_spot
from services.ingestion.participant_profiles import canonical_participant_profile
from services.ingestion.persistence import SnapshotPersistenceResult, persist_observation
from services.providers.base import ProviderError, ProviderResult
from services.providers.khoa import KhoaClient
from services.water_index import (
    Activity,
    CONCRETE_SURF_SKILL_LEVELS,
    EvaluationContext,
    METHODOLOGY_VERSION,
    SafetyStatus,
    SURF_SKILL_LEVEL_UNSPECIFIED,
    assess_surf_skill_evidence,
    canonical_participant_skill_level,
    evaluation_valid_until,
    evaluate_water_index,
)


KST = ZoneInfo("Asia/Seoul")
DAILY_FORECAST_METHODOLOGY_VERSION = "daily-forecast-v1.1.0"
DAILY_REFERENCE_TIME = time(12, 0)
MAX_DAILY_FORECAST_DAYS = 7
KHOA_FORECAST_ACTIVITIES = (Activity.SWIM, Activity.SURF, Activity.MUDFLAT)

PROVIDER_HORIZON_UNAVAILABLE = "PROVIDER_HORIZON_UNAVAILABLE"
REQUIRED_SAFETY_EVIDENCE_MISSING = "REQUIRED_SAFETY_EVIDENCE_MISSING"
FORECAST_EVIDENCE_UNRESOLVED = "FORECAST_EVIDENCE_UNRESOLVED"
ACTIVITY_NOT_SUPPORTED_FOR_SPOT = "ACTIVITY_NOT_SUPPORTED_FOR_SPOT"


@dataclass(frozen=True, slots=True)
class DailyForecastEvaluationReport:
    requested_dates: int
    evaluated_projections: int
    created_projections: int
    updated_projections: int
    unavailable_projections: int
    dry_run: bool


@dataclass(frozen=True, slots=True)
class ForecastEvidenceActivityReport:
    activity: Activity
    fetched_records: int
    matched_records: int
    persisted_records: int
    created_snapshots: int
    skipped_records: int
    provider_failed: bool


@dataclass(frozen=True, slots=True)
class ForecastEvidenceSyncReport:
    activities: tuple[ForecastEvidenceActivityReport, ...]
    dry_run: bool

    @property
    def failed_activities(self) -> tuple[Activity, ...]:
        return tuple(item.activity for item in self.activities if item.provider_failed)

    @property
    def fetched_records(self) -> int:
        return sum(item.fetched_records for item in self.activities)

    @property
    def persisted_records(self) -> int:
        return sum(item.persisted_records for item in self.activities)


class KhoaForecastEvidenceIngestionService:
    """Fetch the provider-advertised KHOA horizon in three bounded products.

    No dates are fabricated and no per-day polling loop is used. Omitting
    ``request_date`` asks each official product for exactly the horizon it
    currently advertises; absent later dates remain absent raw evidence.
    """

    def __init__(
        self,
        client: KhoaClient,
        *,
        persister: Callable[..., SnapshotPersistenceResult] = persist_observation,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        self._client = client
        self._persister = persister
        self._clock = clock

    def sync(
        self,
        *,
        activities: Iterable[Activity | str],
        spots: Sequence[Any],
        dry_run: bool = False,
    ) -> ForecastEvidenceSyncReport:
        normalized = _normalize_khoa_activities(activities)
        fetched_at = self._clock()
        _require_aware(fetched_at, "ingestion clock")
        reports: list[ForecastEvidenceActivityReport] = []
        for activity in normalized:
            try:
                provider_result, adapter = self._fetch(activity)
            except ProviderError:
                reports.append(
                    ForecastEvidenceActivityReport(
                        activity=activity,
                        fetched_records=0,
                        matched_records=0,
                        persisted_records=0,
                        created_snapshots=0,
                        skipped_records=0,
                        provider_failed=True,
                    )
                )
                continue
            reports.append(
                self._persist_activity(
                    activity=activity,
                    provider_result=provider_result,
                    adapter=adapter,
                    spots=spots,
                    fetched_at=fetched_at,
                    dry_run=dry_run,
                )
            )
        return ForecastEvidenceSyncReport(tuple(reports), dry_run=dry_run)

    def _persist_activity(
        self,
        *,
        activity: Activity,
        provider_result: ProviderResult[Any],
        adapter: Callable[..., AdaptedKhoaObservation],
        spots: Sequence[Any],
        fetched_at: datetime,
        dry_run: bool,
    ) -> ForecastEvidenceActivityReport:
        matched = persisted = created = skipped = 0
        seen: set[tuple[Any, str]] = set()
        for record in provider_result.records:
            try:
                observation = adapter(
                    record,
                    fetched_at=fetched_at,
                    endpoint=provider_result.endpoint,
                )
            except KhoaAdapterError:
                skipped += 1
                continue
            spot = match_observation_to_spot(observation, spots)
            if spot is None:
                skipped += 1
                continue
            key = (getattr(spot, "pk", id(spot)), observation.provider_record_id)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            matched += 1
            if dry_run:
                continue
            result = self._persister(spot=spot, observation=observation)
            persisted += 1
            created += int(result.snapshot_created)
        return ForecastEvidenceActivityReport(
            activity=activity,
            fetched_records=len(provider_result.records),
            matched_records=matched,
            persisted_records=persisted,
            created_snapshots=created,
            skipped_records=skipped,
            provider_failed=False,
        )

    def _fetch(
        self,
        activity: Activity,
    ) -> tuple[ProviderResult[Any], Callable[..., AdaptedKhoaObservation]]:
        if activity is Activity.SWIM:
            return self._client.fetch_beach_forecasts(), adapt_beach_forecast
        if activity is Activity.SURF:
            return self._client.fetch_surf_forecasts(), adapt_surf_forecast
        if activity is Activity.MUDFLAT:
            return self._client.fetch_mudflat_forecasts(), adapt_mudflat_forecast
        raise ValueError(f"unsupported KHOA forecast activity: {activity.value}")


def evaluate_daily_forecasts(
    *,
    spots: Sequence[Any],
    activities: Iterable[Activity | str],
    start_date: date,
    days: int = MAX_DAILY_FORECAST_DAYS,
    profiles: Iterable[str] = ("general",),
    skill_levels: Iterable[str] = (
        SURF_SKILL_LEVEL_UNSPECIFIED,
        *CONCRETE_SURF_SKILL_LEVELS,
    ),
    dry_run: bool = False,
    clock: Callable[[], datetime] = timezone.now,
) -> DailyForecastEvaluationReport:
    """Evaluate exact noon instants without filling unsupported provider days."""

    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 7:
        raise ValueError("days must be between 1 and 7")
    normalized_activities = _normalize_activities(activities)
    normalized_profiles = _normalize_profiles(profiles)
    normalized_skill_levels = _normalize_skill_levels(skill_levels)
    evaluated_at = clock()
    _require_aware(evaluated_at, "evaluation clock")

    evaluated = created = updated = unavailable = 0
    for offset in range(days):
        forecast_date = start_date + timedelta(days=offset)
        target_at = datetime.combine(forecast_date, DAILY_REFERENCE_TIME, tzinfo=KST)
        for spot in spots:
            for activity in normalized_activities:
                for participant_profile in normalized_profiles:
                    # Family adds policy only for swimming. Avoid duplicate
                    # representations of identical non-swim decisions in the
                    # default collector run.
                    if participant_profile == "family" and activity is not Activity.SWIM:
                        continue
                    activity_skill_levels = (
                        normalized_skill_levels
                        if activity is Activity.SURF
                        else (SURF_SKILL_LEVEL_UNSPECIFIED,)
                    )
                    for participant_skill_level in activity_skill_levels:
                        values = _projection_values(
                            spot=spot,
                            activity=activity,
                            participant_profile=participant_profile,
                            participant_skill_level=participant_skill_level,
                            target_at=target_at,
                            evaluated_at=evaluated_at,
                        )
                        evaluated += 1
                        unavailable += int(
                            values["availability"] != "available"
                        )
                        if dry_run:
                            continue
                        was_created = _persist_projection(
                            spot=spot,
                            forecast_date=forecast_date,
                            activity=activity,
                            participant_profile=participant_profile,
                            participant_skill_level=participant_skill_level,
                            values=values,
                        )
                        created += int(was_created)
                        updated += int(not was_created)
    return DailyForecastEvaluationReport(
        requested_dates=days,
        evaluated_projections=evaluated,
        created_projections=created,
        updated_projections=updated,
        unavailable_projections=unavailable,
        dry_run=dry_run,
    )


def _projection_values(
    *,
    spot: Any,
    activity: Activity,
    participant_profile: str,
    participant_skill_level: str,
    target_at: datetime,
    evaluated_at: datetime,
) -> dict[str, Any]:
    if not activity_supported_for_spot(spot, activity):
        return _unsupported_projection_values(
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            target_at=target_at,
            evaluated_at=evaluated_at,
        )

    observation = fuse_spot_observations(
        spot=spot,
        at=target_at,
        fetched_at=evaluated_at,
        activity=activity,
    )
    context = EvaluationContext(
        activity=activity,
        at=target_at,
        environment=environment_for_spot(spot),
        participant_profile=participant_profile,
        participant_skill_level=participant_skill_level,
    )
    result = evaluate_water_index(observation.observations, context)
    evidence = _evidence_for_metric_ids(observation.source_metric_ids)
    forecast_evidence = any(item["mode"] == "forecast" for item in evidence)
    surf_skill_reason = ""
    if activity is Activity.SURF:
        assessment = assess_surf_skill_evidence(
            observation.observations,
            participant_skill_level=participant_skill_level,
            at=target_at,
        )
        if not assessment.matched:
            surf_skill_reason = assessment.reason_code
    availability, unavailable_reason = _availability_for_result(
        result=result,
        has_evidence=bool(evidence),
        has_forecast_evidence=forecast_evidence,
        surf_skill_reason=surf_skill_reason,
    )
    evidence_expiries = tuple(
        parsed
        for item in evidence
        if (parsed := _parse_json_datetime(item.get("valid_until"))) is not None
    )
    evidence_starts = tuple(
        parsed
        for item in evidence
        if (parsed := _parse_json_datetime(item.get("valid_from"))) is not None
    )
    valid_until = min(
        (evaluation_valid_until(observation.observations, context), *evidence_expiries)
    )
    valid_from = max(evidence_starts, default=target_at)
    if valid_from > valid_until:
        valid_from = valid_until
    issue_times = tuple(
        parsed
        for item in evidence
        if (parsed := _parse_json_datetime(item.get("issued_at"))) is not None
    )
    fetch_times = tuple(
        parsed
        for item in evidence
        if (parsed := _parse_json_datetime(item.get("fetched_at"))) is not None
    )
    public_state_available = availability == "available"
    public_score_available = public_state_available and result.score is not None
    return {
        "target_at": target_at,
        "score": result.score if public_state_available else None,
        "safety_status": (
            result.safety_status.value if public_state_available else "unknown"
        ),
        "decision": result.decision.value if public_state_available else "unknown",
        "confidence": result.confidence if public_state_available else 0.0,
        "coverage": result.coverage if public_state_available else 0.0,
        "score_range": (
            list(result.score_range)
            if public_score_available and result.score_range
            else []
        ),
        "gates": [_json_value(asdict(item)) for item in result.gates],
        "contributions": (
            [_json_value(asdict(item)) for item in result.contributions]
            if public_score_available
            else []
        ),
        "missing_metrics": list(result.missing_metrics),
        "stale_or_conflicting_metrics": list(
            result.stale_or_conflicting_metrics
        ),
        "limitations": list(result.limitations),
        "availability": availability,
        "unavailable_reason": unavailable_reason,
        "evidence": evidence,
        "evidence_fingerprint": _evidence_fingerprint(
            evidence,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            target_at=target_at,
            unavailable_reason=unavailable_reason,
        ),
        "evidence_issued_at": max(issue_times, default=None),
        "evidence_fetched_at": max(fetch_times, default=None),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "methodology_version": result.methodology_version,
        "projection_methodology_version": DAILY_FORECAST_METHODOLOGY_VERSION,
        "evaluated_at": evaluated_at,
    }


def _unsupported_projection_values(
    *,
    activity: Activity,
    participant_profile: str,
    participant_skill_level: str,
    target_at: datetime,
    evaluated_at: datetime,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    return {
        "target_at": target_at,
        "score": None,
        "safety_status": "unknown",
        "decision": "unknown",
        "confidence": 0.0,
        "coverage": 0.0,
        "score_range": [],
        "gates": [
            {
                "rule_id": "forecast.activity.supported",
                "severity": "unknown",
                "metric_name": "activity",
                "reason_code": ACTIVITY_NOT_SUPPORTED_FOR_SPOT,
            }
        ],
        "contributions": [],
        "missing_metrics": ["activity"],
        "stale_or_conflicting_metrics": [],
        "limitations": [],
        "availability": "unavailable",
        "unavailable_reason": ACTIVITY_NOT_SUPPORTED_FOR_SPOT,
        "evidence": evidence,
        "evidence_fingerprint": _evidence_fingerprint(
            evidence,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            target_at=target_at,
            unavailable_reason=ACTIVITY_NOT_SUPPORTED_FOR_SPOT,
        ),
        "evidence_issued_at": None,
        "evidence_fetched_at": None,
        "valid_from": target_at,
        "valid_until": target_at,
        "methodology_version": METHODOLOGY_VERSION,
        "projection_methodology_version": DAILY_FORECAST_METHODOLOGY_VERSION,
        "evaluated_at": evaluated_at,
    }


@transaction.atomic
def _persist_projection(
    *,
    spot: Any,
    forecast_date: date,
    activity: Activity,
    participant_profile: str,
    participant_skill_level: str,
    values: dict[str, Any],
) -> bool:
    from apps.forecasts.models import DailyForecast

    _, created = DailyForecast.objects.update_or_create(
        spot=spot,
        forecast_date=forecast_date,
        activity=activity.value,
        participant_profile=participant_profile,
        participant_skill_level=participant_skill_level,
        methodology_version=values["methodology_version"],
        projection_methodology_version=values[
            "projection_methodology_version"
        ],
        evidence_fingerprint=values["evidence_fingerprint"],
        defaults=values,
    )
    return created


def _evidence_for_metric_ids(metric_ids: tuple[int, ...]) -> list[dict[str, Any]]:
    if not metric_ids:
        return []
    from apps.conditions.models import ObservationMetric

    metrics = (
        ObservationMetric.objects.select_related("snapshot")
        .filter(pk__in=metric_ids)
        .order_by("snapshot__provider", "snapshot_id", "name", "id")
    )
    return [
        {
            "metric_id": metric.pk,
            "name": metric.name,
            "value": metric.value,
            "unit": metric.unit,
            "mode": metric.mode,
            "state": metric.state,
            "confidence": metric.confidence,
            "provider": metric.snapshot.provider,
            "provider_record_id": metric.snapshot.provider_record_id,
            "ingestion_version": metric.snapshot.ingestion_version,
            "source": metric.source,
            "source_url": metric.source_url,
            "station_id": metric.station_id,
            "spatial_scope": metric.spatial_scope,
            "issued_at": _iso_or_none(metric.snapshot.observed_at),
            "observed_at": _iso_or_none(metric.observed_at),
            "fetched_at": _iso_or_none(metric.fetched_at),
            "valid_from": _iso_or_none(metric.valid_from),
            "valid_until": _iso_or_none(metric.valid_until),
        }
        for metric in metrics
    ]


def _availability_for_result(
    *,
    result: Any,
    has_evidence: bool,
    has_forecast_evidence: bool,
    surf_skill_reason: str = "",
) -> tuple[str, str]:
    if not has_evidence or not has_forecast_evidence:
        return "unavailable", PROVIDER_HORIZON_UNAVAILABLE
    if result.safety_status in {SafetyStatus.STOP, SafetyStatus.CAUTION}:
        # A skill mismatch cannot erase an independently authoritative hazard.
        # These states carry no public suitability score and remain available
        # as the provider-backed STOP/CAUTION signal.
        return "available", ""
    if surf_skill_reason:
        return "partial", surf_skill_reason
    if result.safety_status is not SafetyStatus.UNKNOWN:
        return "available", ""
    if result.stale_or_conflicting_metrics:
        return "partial", FORECAST_EVIDENCE_UNRESOLVED
    return "partial", REQUIRED_SAFETY_EVIDENCE_MISSING


def _evidence_fingerprint(
    evidence: list[dict[str, Any]],
    *,
    activity: Activity,
    participant_profile: str,
    participant_skill_level: str,
    target_at: datetime,
    unavailable_reason: str,
) -> str:
    stable_evidence = [
        {
            key: item.get(key)
            for key in (
                "name",
                "value",
                "unit",
                "mode",
                "state",
                "confidence",
                "provider",
                "provider_record_id",
                "ingestion_version",
                "source",
                "source_url",
                "station_id",
                "spatial_scope",
                "issued_at",
                "observed_at",
                "valid_from",
                "valid_until",
            )
        }
        for item in evidence
    ]
    payload = {
        "activity": activity.value,
        "participant_profile": participant_profile,
        "participant_skill_level": participant_skill_level,
        "target_at": target_at.isoformat(),
        "unavailable_reason": unavailable_reason,
        "evidence": stable_evidence,
        "methodology": DAILY_FORECAST_METHODOLOGY_VERSION,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalize_activities(values: Iterable[Activity | str]) -> tuple[Activity, ...]:
    normalized: list[Activity] = []
    for value in values:
        activity = value if isinstance(value, Activity) else Activity(str(value))
        if activity not in normalized:
            normalized.append(activity)
    if not normalized:
        raise ValueError("at least one activity is required")
    return tuple(normalized)


def _normalize_khoa_activities(
    values: Iterable[Activity | str],
) -> tuple[Activity, ...]:
    normalized = _normalize_activities(values)
    unsupported = tuple(
        item for item in normalized if item not in KHOA_FORECAST_ACTIVITIES
    )
    if unsupported:
        raise ValueError(
            f"unsupported KHOA forecast activity: {unsupported[0].value}"
        )
    return normalized


def _normalize_profiles(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        profile = canonical_participant_profile(value)
        if profile not in normalized:
            normalized.append(profile)
    if not normalized:
        raise ValueError("at least one participant profile is required")
    return tuple(normalized)


def _normalize_skill_levels(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        skill_level = canonical_participant_skill_level(value)
        if skill_level not in normalized:
            normalized.append(skill_level)
    if not normalized:
        raise ValueError("at least one participant skill level is required")
    return tuple(normalized)


def _parse_json_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
