"""Strict boundary for operator-entered official safety observations.

Some safety inputs (for example a beach's current entry or patrol status) do
not have a reliable nationwide machine-readable feed. This module provides an
auditable bridge for a trusted operator to record an official source without
turning a missing value into a fabricated clearance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from services.public_urls import public_https_url
from services.water_index import Metric, MetricMode, MetricState, ObservationSet


INGESTION_VERSION = "operational-observation-v1"
MAX_VALIDITY = timedelta(hours=24)

SOURCE_METRICS: dict[str, frozenset[str]] = {
    "LOCAL_AUTHORITY": frozenset(
        {
            "official_stop_signal",
            "access_status",
            "official_entry_status",
            "patrol_status",
            "designated_swim_zone_status",
            "facility_status",
            "operator_status",
            "weather_alert_level",
            "lightning_clearance_minutes",
            "water_quality_status",
            "water_temperature_c",
            "river_risk_level",
            "river_flow_cms",
            "tide_window_open",
            "marine_hazard_status",
            "fog_status",
            "designated_route_status",
            "facility_hygiene_status",
            "hot_tub_temperature_c",
            "safety_equipment_status",
            "upstream_rain_risk",
        }
    ),
    "OFFICIAL_LOCAL": frozenset(
        {
            "official_stop_signal",
            "access_status",
            "official_entry_status",
            "patrol_status",
            "designated_swim_zone_status",
            "facility_status",
            "operator_status",
            "lightning_clearance_minutes",
            "water_quality_status",
            "water_temperature_c",
            "river_risk_level",
            "river_flow_cms",
            "marine_hazard_status",
            "fog_status",
            "designated_route_status",
            "facility_hygiene_status",
            "hot_tub_temperature_c",
            "safety_equipment_status",
            "upstream_rain_risk",
        }
    ),
    "KMA_WARNING": frozenset(
        {
            "official_stop_signal",
            "weather_alert_level",
            "marine_hazard_status",
            "fog_status",
            "upstream_rain_risk",
        }
    ),
    "KMA_LIGHTNING": frozenset({"lightning_clearance_minutes"}),
    "MOE": frozenset(
        {
            "water_quality_status",
            "water_temperature_c",
            "river_risk_level",
            "river_flow_cms",
            "upstream_rain_risk",
        }
    ),
    "FACILITY_OPERATOR": frozenset(
        {
            "access_status",
            "facility_status",
            "operator_status",
            "water_temperature_c",
            "facility_hygiene_status",
            "hot_tub_temperature_c",
            "safety_equipment_status",
        }
    ),
}

_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_METRIC_NAME = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


@dataclass(frozen=True, slots=True)
class OperationalObservation:
    provider: str
    provider_record_id: str
    ingestion_version: str
    state: str
    source_observed_at: datetime
    fetched_at: datetime
    valid_from: datetime
    valid_until: datetime
    spatial_scope: str
    source_url: str
    observations: ObservationSet


def build_operational_observation(
    *,
    source: str,
    provider_record_id: str,
    source_url: str,
    spatial_scope: str,
    observed_at: datetime,
    fetched_at: datetime,
    valid_until: datetime,
    metric_assignments: Iterable[str],
    confidence: float = 1.0,
) -> OperationalObservation:
    """Validate and normalize one official operational update.

    Values are intentionally not interpreted as clearance here. The Water
    Index engine owns semantic validation and will return UNKNOWN for an
    unrecognized value. This boundary controls who may assert each metric and
    ensures every assertion is traceable and expires.
    """

    canonical_source = _canonical_source(source)
    allowed = SOURCE_METRICS.get(canonical_source)
    if allowed is None:
        raise ValueError("source is not approved for operational observations")
    if not _RECORD_ID.fullmatch(provider_record_id):
        raise ValueError("record id must use 1-160 safe identifier characters")
    _validate_public_source_url(source_url)
    if not spatial_scope.strip() or len(spatial_scope) > 200:
        raise ValueError("spatial scope is required and must be at most 200 characters")
    _require_aware(observed_at, "observed_at")
    _require_aware(fetched_at, "fetched_at")
    _require_aware(valid_until, "valid_until")
    if observed_at > fetched_at:
        raise ValueError("observed_at cannot be later than fetched_at")
    if valid_until <= fetched_at:
        raise ValueError("valid_until must be later than fetched_at")
    if valid_until - observed_at > MAX_VALIDITY:
        raise ValueError("operational observations cannot be valid for over 24 hours")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a finite number from 0.8 to 1.0")
    normalized_confidence = float(confidence)
    if not math.isfinite(normalized_confidence) or not 0.8 <= normalized_confidence <= 1.0:
        raise ValueError("confidence must be a finite number from 0.8 to 1.0")

    metrics: list[Metric] = []
    names: set[str] = set()
    for assignment in metric_assignments:
        name, value = _parse_assignment(assignment)
        if name not in allowed:
            raise ValueError(f"{canonical_source} is not approved for metric {name}")
        if name == "adult_supervision_status":
            raise ValueError("adult supervision is session context and cannot be stored")
        if name in names:
            raise ValueError(f"duplicate metric assignment: {name}")
        names.add(name)
        metrics.append(
            Metric(
                name=name,
                value=value,
                unit=_metric_unit(name),
                source=canonical_source,
                source_url=source_url,
                station_id=provider_record_id,
                spatial_scope=spatial_scope.strip(),
                observed_at=observed_at,
                fetched_at=fetched_at,
                valid_from=observed_at,
                valid_until=valid_until,
                mode=MetricMode.OBSERVED,
                state=MetricState.VALID,
                confidence=normalized_confidence,
            )
        )
    if not metrics:
        raise ValueError("at least one metric assignment is required")

    return OperationalObservation(
        provider=canonical_source,
        provider_record_id=provider_record_id,
        ingestion_version=INGESTION_VERSION,
        state="live",
        source_observed_at=observed_at,
        fetched_at=fetched_at,
        valid_from=observed_at,
        valid_until=valid_until,
        spatial_scope=spatial_scope.strip(),
        source_url=source_url,
        observations=ObservationSet.from_metrics(*metrics),
    )


def _parse_assignment(assignment: Any) -> tuple[str, str | float | bool]:
    if not isinstance(assignment, str) or "=" not in assignment:
        raise ValueError("metrics must use NAME=VALUE")
    raw_name, raw_value = assignment.split("=", 1)
    name = raw_name.strip().lower().replace("-", "_")
    value_text = raw_value.strip()
    if not _METRIC_NAME.fullmatch(name):
        raise ValueError("metric name is invalid")
    if not value_text or len(value_text) > 200 or any(ord(char) < 32 for char in value_text):
        raise ValueError(f"metric {name} must have a short printable value")
    canonical = value_text.casefold()
    if canonical == "true":
        return name, True
    if canonical == "false":
        return name, False
    try:
        number = float(value_text)
    except ValueError:
        return name, value_text
    if not math.isfinite(number):
        raise ValueError(f"metric {name} numeric value must be finite")
    return name, number


def _metric_unit(name: str) -> str:
    # A hydraulic producer may consume only an explicitly typed volumetric
    # flow. Generic "canonical" numbers must never be compared with m3/s
    # calibration thresholds.
    if name == "river_flow_cms":
        return "m3/s"
    return "canonical"


def _validate_public_source_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
    except (TypeError, ValueError):
        raise ValueError("source URL must be a public HTTPS URL without query data") from None
    if (
        not public_https_url(value)
        or parsed.query
        or parsed.fragment
        or "\\" in value
    ):
        raise ValueError("source URL must be a public HTTPS URL without query data")


def _canonical_source(value: Any) -> str:
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
