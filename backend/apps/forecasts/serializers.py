from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.spots.models import WaterSpot
from services.public_urls import public_https_url
from services.water_index import (
    Activity,
    Metric,
    MetricMode,
    MetricState,
    SURF_GRADE_DETAIL_MISSING,
    SURF_OFFICIAL_GRADE_MISSING,
    SURF_SKILL_LEVEL_REQUIRED,
    assess_surf_skill_evidence,
)

from .models import DailyForecast, WaterForecast


FORECAST_EVIDENCE_EXPIRED = "FORECAST_EVIDENCE_EXPIRED"
FORECAST_EVIDENCE_NOT_YET_FETCHED = "FORECAST_EVIDENCE_NOT_YET_FETCHED"
FORECAST_EXPIRY_UNAVAILABLE = "FORECAST_EXPIRY_UNAVAILABLE"

class WaterForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterForecast
        fields = "__all__"


class DailyForecastQuerySerializer(serializers.Serializer):
    spot = serializers.PrimaryKeyRelatedField(queryset=WaterSpot.objects.all())
    activity = serializers.ChoiceField(choices=[item.value for item in Activity])
    participant_profile = serializers.ChoiceField(
        choices=("general", "family"),
        default="general",
    )
    participant_skill_level = serializers.ChoiceField(
        choices=("unspecified", "beginner", "intermediate", "advanced"),
        default="unspecified",
    )
    start_date = serializers.DateField(required=False)
    days = serializers.IntegerField(min_value=1, max_value=7, default=7)

    def validate_start_date(self, value):
        as_of = self.context.get("as_of") or timezone.now()
        if value < timezone.localdate(as_of):
            raise serializers.ValidationError(
                "start_date cannot be earlier than the current local date."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        activity = attrs.get("activity")
        participant_profile = attrs.get("participant_profile", "general")
        participant_skill_level = attrs.get(
            "participant_skill_level",
            "unspecified",
        )
        if activity != Activity.SURF.value and (
            participant_skill_level != "unspecified"
        ):
            raise serializers.ValidationError(
                {
                    "participant_skill_level": (
                        "A concrete participant skill level is supported only "
                        "for surfing forecasts."
                    )
                }
            )
        if activity != Activity.SWIM.value and participant_profile == "family":
            raise serializers.ValidationError(
                {
                    "participant_profile": (
                        "The family forecast profile applies only to swimming."
                    )
                }
            )
        return attrs


def daily_forecast_payload(
    forecast: DailyForecast,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Return the effective, request-time-safe public forecast projection."""

    failure_reason = _effective_failure_reason(forecast, as_of=as_of)
    evidence = [_public_evidence(item) for item in forecast.evidence]
    surf_skill_reason = _surf_skill_failure_reason(
        forecast,
        evidence=evidence,
        as_of=as_of,
    )
    availability_reason = (
        forecast.unavailable_reason
        if forecast.availability != DailyForecast.Availability.AVAILABLE
        else ""
    )
    surf_blocks_public_state = bool(
        surf_skill_reason
        and forecast.safety_status
        not in {
            DailyForecast.SafetyStatus.STOP,
            DailyForecast.SafetyStatus.CAUTION,
        }
    )
    hard_unknown = bool(
        failure_reason or availability_reason or surf_blocks_public_state
    )
    suitability_unknown = bool(
        hard_unknown or surf_skill_reason or forecast.score is None
    )
    effective_reason = failure_reason or availability_reason or surf_skill_reason
    gates = list(forecast.gates)
    missing_metrics = list(forecast.missing_metrics)
    stale_metrics = list(forecast.stale_or_conflicting_metrics)
    if effective_reason and not any(
        isinstance(gate, dict)
        and gate.get("reason_code") == effective_reason
        for gate in gates
    ):
        gates = [
            {
                "rule_id": (
                    "suitability.surf.skill_grade"
                    if effective_reason == surf_skill_reason
                    else "forecast.evidence.current"
                ),
                "severity": "unknown",
                "metric_name": (
                    "participant_skill_level"
                    if effective_reason == SURF_SKILL_LEVEL_REQUIRED
                    else "forecast_evidence"
                ),
                "reason_code": effective_reason,
            },
            *gates,
        ]
    if failure_reason is not None:
        stale_metrics = list(
            dict.fromkeys([*stale_metrics, "forecast_evidence"])
        )
    if surf_skill_reason:
        metric_name = (
            "participant_skill_level"
            if surf_skill_reason == SURF_SKILL_LEVEL_REQUIRED
            else "official_activity_grade"
            if surf_skill_reason == SURF_OFFICIAL_GRADE_MISSING
            else "official_grade_detail"
        )
        target = (
            missing_metrics
            if surf_skill_reason
            in {
                SURF_SKILL_LEVEL_REQUIRED,
                SURF_OFFICIAL_GRADE_MISSING,
                SURF_GRADE_DETAIL_MISSING,
            }
            else stale_metrics
        )
        if metric_name not in target:
            target.append(metric_name)

    safety_status = "unknown" if hard_unknown else forecast.safety_status
    if hard_unknown:
        decision = "unknown"
    elif surf_skill_reason and safety_status == DailyForecast.SafetyStatus.CLEAR:
        decision = "unknown"
    else:
        decision = forecast.decision
    score = (
        None
        if suitability_unknown or safety_status in {"stop", "unknown"}
        else forecast.score
    )
    availability = (
        "unavailable" if failure_reason else forecast.availability
    )
    if surf_blocks_public_state and (
        availability == DailyForecast.Availability.AVAILABLE
    ):
        availability = "partial"
    unavailable_reason = effective_reason or forecast.unavailable_reason
    return {
        "id": forecast.pk,
        "spot": forecast.spot_id,
        "spot_name": forecast.spot.name,
        "forecast_date": forecast.forecast_date,
        "activity": forecast.activity,
        "participant_profile": forecast.participant_profile,
        "participant_skill_level": forecast.participant_skill_level,
        "target_at": forecast.target_at,
        "score": score,
        "suitability_score": score,
        "safety_status": safety_status,
        "decision": decision,
        "confidence": 0.0 if hard_unknown else forecast.confidence,
        "coverage": 0.0 if hard_unknown else forecast.coverage,
        "score_range": [] if suitability_unknown else forecast.score_range,
        "gates": gates,
        "contributions": [] if suitability_unknown else forecast.contributions,
        "missing_metrics": missing_metrics,
        "stale_or_conflicting_metrics": stale_metrics,
        "limitations": forecast.limitations,
        "availability": availability,
        "unavailable_reason": unavailable_reason,
        "providers": sorted(
            {
                str(item.get("provider", "")).strip()
                for item in evidence
                if str(item.get("provider", "")).strip()
            }
        ),
        "evidence_issued_at": forecast.evidence_issued_at,
        "evidence_fetched_at": forecast.evidence_fetched_at,
        "valid_from": forecast.valid_from,
        "valid_until": forecast.valid_until,
        "methodology_version": forecast.methodology_version,
        "projection_methodology_version": (
            forecast.projection_methodology_version
        ),
        "evaluated_at": forecast.evaluated_at,
        "computed_at": forecast.computed_at,
        "updated_at": forecast.updated_at,
        "evidence": evidence,
    }


def _effective_failure_reason(
    forecast: DailyForecast,
    *,
    as_of: datetime,
) -> str | None:
    # Availability is projected separately. This function covers the stronger
    # case where a previously available row has aged out at request time.
    if forecast.availability != DailyForecast.Availability.AVAILABLE:
        return None
    if forecast.evidence_fetched_at is None:
        return FORECAST_EXPIRY_UNAVAILABLE
    if forecast.evidence_fetched_at > as_of:
        return FORECAST_EVIDENCE_NOT_YET_FETCHED
    if forecast.valid_until is None:
        return FORECAST_EXPIRY_UNAVAILABLE
    if as_of > forecast.valid_until:
        return FORECAST_EVIDENCE_EXPIRED
    return None


def _surf_skill_failure_reason(
    forecast: DailyForecast,
    *,
    evidence: list[dict[str, Any]],
    as_of: datetime,
) -> str:
    if forecast.activity != DailyForecast.Activity.SURF:
        return ""
    metrics = tuple(
        metric
        for item in evidence
        if (metric := _domain_metric_from_evidence(item)) is not None
    )
    assessment = assess_surf_skill_evidence(
        metrics,
        participant_skill_level=forecast.participant_skill_level,
        at=forecast.target_at if forecast.target_at > as_of else as_of,
    )
    return "" if assessment.matched else assessment.reason_code


def _domain_metric_from_evidence(item: Any) -> Metric | None:
    if not isinstance(item, dict) or item.get("value") is None:
        return None
    try:
        observed_at = _parse_evidence_datetime(item.get("observed_at"))
        fetched_at = _parse_evidence_datetime(item.get("fetched_at"))
        valid_from = _parse_evidence_datetime(item.get("valid_from"))
        valid_until = _parse_evidence_datetime(item.get("valid_until"))
        if observed_at is None or fetched_at is None:
            return None
        return Metric(
            name=str(item.get("name", "")),
            value=item["value"],
            unit=str(item.get("unit", "")),
            source=str(item.get("source", "")),
            source_url=str(item.get("source_url", "")),
            station_id=str(item.get("station_id", "")),
            spatial_scope=str(item.get("spatial_scope", "")),
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            mode=MetricMode(str(item.get("mode", "observed"))),
            confidence=float(item.get("confidence", 0.0)),
            state=MetricState(str(item.get("state", "invalid"))),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_evidence_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    if not isinstance(value, str):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _public_evidence(value: Any) -> Any:
    if isinstance(value, list):
        return [_public_evidence(item) for item in value]
    if isinstance(value, dict):
        public: dict[str, Any] = {}
        for key, item in value.items():
            canonical = str(key).strip().lower()
            if canonical in {
                "api_key",
                "apikey",
                "authorization",
                "headers",
                "raw_payload",
                "request",
                "response",
                "service_key",
                "servicekey",
            }:
                continue
            public[key] = (
                public_https_url(item)
                if canonical == "source_url"
                else _public_evidence(item)
            )
        return public
    return value
