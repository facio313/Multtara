"""Evidence-bound producers for global suitability metrics.

Every output in this module is a convenience/suitability factor. None is a
safety clearance. Producers abstain when source identity, time, spatial scope,
unit, catalog verification, or calibration evidence is incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

from services.public_urls import public_https_url
from services.water_index import (
    Metric,
    MetricMode,
    MetricState,
    ObservationSet,
    calculate_hci_beach,
    humidex_from_dew_point,
)

from .fusion import DERIVED_PROVIDER
from .persistence import (
    MetricLineageInput,
    SnapshotPersistenceResult,
    persist_observation,
)


DERIVATION_VERSION = "suitability-derivation-v1"
HCI_MAX_AGE = timedelta(hours=3)
FACILITY_MAX_AGE = timedelta(minutes=30)
FLOW_MAX_AGE = timedelta(minutes=15)
_LINEAGE_PRIORITY = 110

_HCI_INPUTS = frozenset(
    {
        "air_temperature_c",
        "relative_humidity_pct",
        "sky_condition_code",
        "precipitation_amount_text",
        "daily_precipitation_mm",
        "wind_speed_ms",
    }
)
_HCI_OUTPUTS = (
    "hci_beach_score",
    "hci_beach_thermal_component",
    "hci_beach_aesthetic_component",
    "hci_beach_precipitation_component",
    "hci_beach_wind_component",
    "hci_beach_dew_point_c",
    "hci_beach_humidex",
    "hci_beach_cloud_cover_upper_pct",
)
_FACILITY_SOURCES = frozenset({"FACILITY_OPERATOR", "LOCAL_AUTHORITY"})
_OPEN_OPERATION_VALUES = frozenset(
    {"open", "active", "operating", "영업", "운영", "정상"}
)
_CLOSED_OPERATION_VALUES = frozenset(
    {"closed", "suspended", "restricted", "휴업", "운휴", "통제", "폐쇄"}
)


@dataclass(frozen=True, slots=True)
class KmaPrecipitationInterval:
    """Exact public meaning of one KMA PCP category, not a daily total."""

    lower_mm: float
    upper_mm: float | None
    upper_inclusive: bool


@dataclass(frozen=True, slots=True)
class DerivedObservation:
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
    metric_lineage: tuple[MetricLineageInput, ...]


@dataclass(frozen=True, slots=True)
class SuitabilityDerivationReport:
    observations: tuple[DerivedObservation, ...]
    persistence: tuple[SnapshotPersistenceResult, ...]
    dry_run: bool

    @property
    def derived_snapshots(self) -> int:
        return len(self.observations)

    @property
    def persisted_snapshots(self) -> int:
        return len(self.persistence)


def derive_suitability_metrics_for_spot(
    *,
    spot: Any,
    at: datetime,
    dry_run: bool = False,
) -> SuitabilityDerivationReport:
    """Derive every currently evidenced global factor for one spot."""

    _require_aware(at, "at")
    observations: list[DerivedObservation] = list(
        derive_hci_beach_observations(spot=spot, at=at)
    )
    if facility := derive_facility_fit_observation(spot=spot, at=at):
        observations.append(facility)
    if flow := derive_flow_suitability_observation(spot=spot, at=at):
        observations.append(flow)
    persisted: list[SnapshotPersistenceResult] = []
    if not dry_run:
        for observation in observations:
            persisted.append(persist_observation(spot=spot, observation=observation))
    return SuitabilityDerivationReport(
        observations=tuple(observations),
        persistence=tuple(persisted),
        dry_run=dry_run,
    )


def derive_hci_beach_observations(
    *,
    spot: Any,
    at: datetime,
) -> tuple[DerivedObservation, ...]:
    """Return HCI:Beach only for complete, co-temporal typed KMA evidence.

    KMA PCP is an interval precipitation category, not a daily total. Therefore
    PCP is interpreted for consistency but never promoted into the required
    ``daily_precipitation_mm`` input. An explicit daily total must coexist in
    the exact same KMA snapshot/window or this producer returns nothing.
    """

    _require_aware(at, "at")
    if str(getattr(spot, "type", "")).strip().lower() != "beach":
        return ()
    from apps.conditions.models import ObservationSnapshot

    snapshots = (
        ObservationSnapshot.objects.prefetch_related("metrics")
        .filter(
            spot=spot,
            provider="KMA",
            state=ObservationSnapshot.SourceState.LIVE,
            fetched_at__lte=at,
            valid_until__gte=at,
        )
        .order_by("valid_from", "observed_at", "fetched_at", "pk")
    )
    return tuple(
        observation
        for snapshot in snapshots
        if (observation := _hci_from_snapshot(snapshot, at=at)) is not None
    )


def _hci_from_snapshot(snapshot: Any, *, at: datetime) -> DerivedObservation | None:
    rows = {row.name: row for row in snapshot.metrics.all()}
    if not _HCI_INPUTS.issubset(rows):
        return None
    selected = tuple(rows[name] for name in sorted(_HCI_INPUTS))
    if not _same_kma_window(selected, snapshot=snapshot, at=at):
        return None

    temperature = _number(rows["air_temperature_c"], unit="degC")
    humidity = _number(rows["relative_humidity_pct"], unit="percent")
    daily_rain = _number(rows["daily_precipitation_mm"], unit="mm")
    wind_ms = _number(rows["wind_speed_ms"], unit="m/s")
    cloud_upper = kma_sky_cloud_cover_upper_pct(rows["sky_condition_code"].value)
    pcp = parse_kma_pcp_interval(rows["precipitation_amount_text"].value)
    if any(
        item is None
        for item in (temperature, humidity, daily_rain, wind_ms, cloud_upper, pcp)
    ):
        return None
    assert temperature is not None
    assert humidity is not None
    assert daily_rain is not None
    assert wind_ms is not None
    assert cloud_upper is not None
    assert pcp is not None
    if not (-80 <= temperature <= 60):
        return None
    if not (0 < humidity <= 100):
        return None
    if not (0 <= daily_rain <= 2_000) or not (0 <= wind_ms <= 100):
        return None
    # One interval's lower bound cannot exceed its evidenced daily total. The
    # inverse is not required: a daily total may include other intervals.
    if pcp.lower_mm > daily_rain + 1e-9:
        return None

    try:
        dew_point = dew_point_from_relative_humidity(
            air_temperature_c=temperature,
            relative_humidity_pct=humidity,
        )
        humidex = humidex_from_dew_point(temperature, dew_point)
        result = calculate_hci_beach(
            humidex=humidex,
            cloud_cover_pct=cloud_upper,
            daily_precipitation_mm=daily_rain,
            average_wind_kmh=wind_ms * 3.6,
        )
    except (OverflowError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not all(math.isfinite(item) for item in (dew_point, humidex)):
        return None

    confidence = min(float(row.confidence) for row in selected)
    observed_at = max(row.observed_at for row in selected)
    mode = MetricMode(selected[0].mode)
    source_url = _common_public_source_url(selected)
    station_id = selected[0].station_id
    scope = selected[0].spatial_scope
    valid_from = snapshot.valid_from
    valid_until = snapshot.valid_until
    assert valid_from is not None and valid_until is not None

    values = {
        "hci_beach_score": (float(result.score), "points"),
        "hci_beach_thermal_component": (float(result.thermal_comfort), "points"),
        "hci_beach_aesthetic_component": (float(result.aesthetic), "points"),
        "hci_beach_precipitation_component": (
            float(result.precipitation),
            "points",
        ),
        "hci_beach_wind_component": (float(result.wind), "points"),
        "hci_beach_dew_point_c": (dew_point, "degC"),
        "hci_beach_humidex": (humidex, "index"),
        "hci_beach_cloud_cover_upper_pct": (cloud_upper, "percent"),
    }
    metrics = tuple(
        _derived_metric(
            name=name,
            value=value,
            unit=unit,
            observed_at=observed_at,
            fetched_at=at,
            valid_from=valid_from,
            valid_until=valid_until,
            mode=mode,
            confidence=confidence,
            source_url=source_url,
            station_id=station_id,
            spatial_scope=scope,
        )
        for name, (value, unit) in values.items()
    )
    all_ids = tuple(sorted(row.pk for row in selected))
    temp_humidity_ids = (
        rows["air_temperature_c"].pk,
        rows["relative_humidity_pct"].pk,
    )
    lineage_ids = {
        "hci_beach_score": all_ids,
        "hci_beach_thermal_component": temp_humidity_ids,
        "hci_beach_aesthetic_component": (rows["sky_condition_code"].pk,),
        "hci_beach_precipitation_component": (
            rows["precipitation_amount_text"].pk,
            rows["daily_precipitation_mm"].pk,
        ),
        "hci_beach_wind_component": (rows["wind_speed_ms"].pk,),
        "hci_beach_dew_point_c": temp_humidity_ids,
        "hci_beach_humidex": temp_humidity_ids,
        "hci_beach_cloud_cover_upper_pct": (
            rows["sky_condition_code"].pk,
        ),
    }
    payload = {
        "kind": "hci_beach",
        "source_metric_ids": all_ids,
        "sources": [_metric_identity(row) for row in selected],
        "values": values,
        "sky_upper_pct": cloud_upper,
        "pcp": (pcp.lower_mm, pcp.upper_mm, pcp.upper_inclusive),
        "window": (valid_from.isoformat(), valid_until.isoformat()),
        "version": DERIVATION_VERSION,
    }
    return DerivedObservation(
        provider=DERIVED_PROVIDER,
        provider_record_id=f"hci-beach:{_fingerprint(payload)}",
        ingestion_version=DERIVATION_VERSION,
        state="live",
        source_observed_at=observed_at,
        fetched_at=at,
        valid_from=valid_from,
        valid_until=valid_until,
        spatial_scope=scope,
        source_url=source_url,
        observations=ObservationSet.from_metrics(*metrics),
        metric_lineage=_lineage(lineage_ids),
    )


def derive_facility_fit_observation(
    *,
    spot: Any,
    at: datetime,
) -> DerivedObservation | None:
    """Derive only globally evidenced facility operation/shelter factors."""

    _require_aware(at, "at")
    if str(getattr(spot, "type", "")).strip().lower() != "hotspring":
        return None
    if not _verified_facility_catalog(spot, at=at):
        return None
    from apps.conditions.models import ObservationMetric

    rows = (
        ObservationMetric.objects.select_related("snapshot")
        .filter(snapshot__spot=spot, name="facility_status")
        .order_by("-observed_at", "-fetched_at", "-pk")
    )
    candidates = tuple(
        row
        for row in rows
        if _official_metric_is_current(
            row,
            at=at,
            max_age=FACILITY_MAX_AGE,
            allowed_sources=_FACILITY_SOURCES,
            required_scope=f"spot:{spot.pk}",
            required_unit=None,
        )
    )
    newest_by_source: dict[str, Any] = {}
    for row in candidates:
        newest_by_source.setdefault(_canonical_source(row.source), row)
    evidence = tuple(newest_by_source.values())
    if not evidence:
        return None
    statuses = tuple(_operation_status(row.value) for row in evidence)
    if any(status != "open" for status in statuses):
        return None

    winner = max(
        evidence,
        key=lambda row: (
            1 if _canonical_source(row.source) == "LOCAL_AUTHORITY" else 0,
            row.observed_at,
            row.fetched_at,
            row.pk,
        ),
    )
    confidence = min(
        float(getattr(spot, "catalog_confidence", 0.0)),
        *(float(row.confidence) for row in evidence),
    )
    valid_from = max(
        row.valid_from or row.observed_at
        for row in evidence
    )
    valid_until = min(
        _effective_expiry(row, max_age=FACILITY_MAX_AGE)
        for row in evidence
    )
    if valid_until < valid_from or not valid_from <= at <= valid_until:
        return None
    observed_at = max(row.observed_at for row in evidence)
    values = {
        "facility_operation_confidence": (confidence, "proportion"),
    }
    # Legacy False booleans cannot distinguish an evidenced absence from an
    # unfilled catalog field. Emit shelter only for the explicit positive pair.
    if bool(getattr(spot, "indoor", False)) and bool(
        getattr(spot, "bad_weather_suitable", False)
    ):
        values["indoor_weather_shelter"] = (1.0, "proportion")
    catalog_source_url = public_https_url(spot.catalog_source_url)
    metrics = tuple(
        _derived_metric(
            name=name,
            value=value,
            unit=unit,
            observed_at=observed_at,
            fetched_at=at,
            valid_from=valid_from,
            valid_until=valid_until,
            mode=MetricMode.OBSERVED,
            confidence=confidence,
            # The derived row retains catalog provenance directly; the
            # time-sensitive operator URL remains reachable through lineage.
            source_url=catalog_source_url,
            station_id=winner.station_id,
            spatial_scope=winner.spatial_scope,
        )
        for name, (value, unit) in values.items()
    )
    source_ids = tuple(sorted(row.pk for row in evidence))
    payload = {
        "kind": "facility_fit",
        "catalog": {
            "confidence": float(spot.catalog_confidence),
            "indoor": bool(spot.indoor),
            "bad_weather_suitable": bool(spot.bad_weather_suitable),
            "source": str(spot.catalog_source),
            "source_url": str(spot.catalog_source_url),
            "verified_at": spot.catalog_verified_at.isoformat(),
        },
        "source_metric_ids": source_ids,
        "sources": [_metric_identity(row) for row in evidence],
        "values": values,
        "version": DERIVATION_VERSION,
    }
    return DerivedObservation(
        provider=DERIVED_PROVIDER,
        provider_record_id=f"facility-fit:{_fingerprint(payload)}",
        ingestion_version=DERIVATION_VERSION,
        state="live",
        source_observed_at=observed_at,
        fetched_at=at,
        valid_from=valid_from,
        valid_until=valid_until,
        spatial_scope=winner.spatial_scope,
        source_url=catalog_source_url,
        observations=ObservationSet.from_metrics(*metrics),
        metric_lineage=_lineage(
            {name: source_ids for name in values}
        ),
    )


def derive_flow_suitability_observation(
    *,
    spot: Any,
    at: datetime,
) -> DerivedObservation | None:
    """Apply an active site calibration to one matching official flow metric."""

    _require_aware(at, "at")
    if str(getattr(spot, "type", "")).strip().lower() not in {"river", "valley"}:
        return None
    from apps.conditions.models import HydraulicCalibration, ObservationMetric

    calibration = (
        HydraulicCalibration.objects.filter(
            spot=spot,
            active=True,
            verified=True,
            verified_at__isnull=False,
            verified_at__lte=at,
        )
        .order_by("-verified_at", "-pk")
        .first()
    )
    if calibration is None:
        return None
    try:
        calibration.full_clean()
    except ValidationError:
        return None

    rows = (
        ObservationMetric.objects.select_related("snapshot")
        .filter(snapshot__spot=spot, name="river_flow_cms")
        .order_by("-observed_at", "-fetched_at", "-pk")
    )
    candidates = tuple(
        row
        for row in rows
        if _official_metric_is_current(
            row,
            at=at,
            max_age=FLOW_MAX_AGE,
            allowed_sources=frozenset({calibration.authority}),
            required_scope=calibration.spatial_scope,
            required_unit="m3/s",
        )
        and row.station_id == calibration.station_id
    )
    if not candidates:
        return None
    winner = candidates[0]
    same_revision = tuple(
        row
        for row in candidates
        if row.observed_at == winner.observed_at and row.fetched_at == winner.fetched_at
    )
    numeric_values = tuple(_number(row, unit="m3/s") for row in same_revision)
    if any(value is None for value in numeric_values):
        return None
    if len({float(value) for value in numeric_values if value is not None}) != 1:
        return None
    flow = _number(winner, unit="m3/s")
    if flow is None or flow < 0:
        return None
    score = flow_suitability_score(
        flow_cms=flow,
        q_min=calibration.q_min,
        q_opt_low=calibration.q_opt_low,
        q_opt_high=calibration.q_opt_high,
        q_max=calibration.q_max,
    )
    valid_from = winner.valid_from or winner.observed_at
    valid_until = _effective_expiry(winner, max_age=FLOW_MAX_AGE)
    if valid_until < valid_from or not valid_from <= at <= valid_until:
        return None
    metric = _derived_metric(
        name="flow_suitability_score",
        value=score,
        unit="points",
        observed_at=winner.observed_at,
        fetched_at=at,
        valid_from=valid_from,
        valid_until=valid_until,
        mode=MetricMode.OBSERVED,
        confidence=float(winner.confidence),
        source_url=calibration.evidence_url,
        station_id=calibration.station_id,
        spatial_scope=calibration.spatial_scope,
    )
    payload = {
        "kind": "flow_suitability",
        "calibration": {
            "id": calibration.pk,
            "version": calibration.version,
            "station_id": calibration.station_id,
            "scope": calibration.spatial_scope,
            "authority": calibration.authority,
            "thresholds": (
                calibration.q_min,
                calibration.q_opt_low,
                calibration.q_opt_high,
                calibration.q_max,
            ),
            "evidence_url": calibration.evidence_url,
        },
        "source_metric_id": winner.pk,
        "source": _metric_identity(winner),
        "flow": flow,
        "score": score,
        "version": DERIVATION_VERSION,
    }
    return DerivedObservation(
        provider=DERIVED_PROVIDER,
        provider_record_id=f"flow-fit:{_fingerprint(payload)}",
        ingestion_version=DERIVATION_VERSION,
        state="live",
        source_observed_at=winner.observed_at,
        fetched_at=at,
        valid_from=valid_from,
        valid_until=valid_until,
        spatial_scope=calibration.spatial_scope,
        source_url=calibration.evidence_url,
        observations=ObservationSet.from_metrics(metric),
        metric_lineage=_lineage(
            {"flow_suitability_score": (winner.pk,)}
        ),
    )


def dew_point_from_relative_humidity(
    *,
    air_temperature_c: float,
    relative_humidity_pct: float,
) -> float:
    """Magnus conversion used before the published Humidex calculation."""

    temperature = float(air_temperature_c)
    humidity = float(relative_humidity_pct)
    if not math.isfinite(temperature) or not math.isfinite(humidity):
        raise ValueError("temperature and relative humidity must be finite")
    if not -80 <= temperature <= 60 or not 0 < humidity <= 100:
        raise ValueError("temperature or relative humidity is outside supported range")
    a = 17.625
    b = 243.04
    gamma = math.log(humidity / 100.0) + (a * temperature) / (b + temperature)
    denominator = a - gamma
    if denominator == 0:
        raise ValueError("relative humidity conversion is undefined")
    return b * gamma / denominator


def kma_sky_cloud_cover_upper_pct(value: Any) -> float | None:
    """Map official KMA SKY categories to conservative cloud-cover bounds.

    KMA categories are 1=clear (0--5 tenths), 3=mostly cloudy (6--8), and
    4=cloudy (9--10). HCI needs a percentage, so the upper category bound is
    used. This deliberately avoids presenting a categorical forecast as an
    exact cloud observation.
    """

    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    return {1: 50.0, 3: 80.0, 4: 100.0}.get(int(numeric))


_PCP_LESS = re.compile(r"^1(?:\.0+)?\s*mm\s*미만$", re.IGNORECASE)
_PCP_RANGE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*mm$",
    re.IGNORECASE,
)
_PCP_ABOVE = re.compile(r"^(\d+(?:\.\d+)?)\s*mm\s*이상$", re.IGNORECASE)
_PCP_EXACT = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$", re.IGNORECASE)


def parse_kma_pcp_interval(value: Any) -> KmaPrecipitationInterval | None:
    """Parse documented KMA PCP display categories without inventing a mean."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0:
            return None
        return KmaPrecipitationInterval(numeric, numeric, True)
    text = " ".join(str(value).strip().split())
    compact = text.replace(" ", "")
    if compact.casefold() in {"강수없음", "없음", "0mm", "0.0mm"}:
        return KmaPrecipitationInterval(0.0, 0.0, True)
    if _PCP_LESS.fullmatch(compact):
        return KmaPrecipitationInterval(0.0, 1.0, False)
    if match := _PCP_RANGE.fullmatch(compact):
        lower, upper = (float(item) for item in match.groups())
        if lower < 0 or upper < lower:
            return None
        return KmaPrecipitationInterval(lower, upper, True)
    if match := _PCP_ABOVE.fullmatch(compact):
        lower = float(match.group(1))
        return KmaPrecipitationInterval(lower, None, False)
    if match := _PCP_EXACT.fullmatch(compact):
        exact = float(match.group(1))
        return KmaPrecipitationInterval(exact, exact, True)
    return None


def flow_suitability_score(
    *,
    flow_cms: float,
    q_min: float,
    q_opt_low: float,
    q_opt_high: float,
    q_max: float,
) -> float:
    """Piecewise site calibration: zero at limits, 100 in the optimum band."""

    values = tuple(float(item) for item in (flow_cms, q_min, q_opt_low, q_opt_high, q_max))
    if not all(math.isfinite(item) for item in values):
        raise ValueError("flow and calibration thresholds must be finite")
    flow, minimum, optimal_low, optimal_high, maximum = values
    if not 0 <= minimum < optimal_low <= optimal_high < maximum:
        raise ValueError("calibration threshold order is invalid")
    if flow <= minimum or flow >= maximum:
        return 0.0
    if flow < optimal_low:
        return 100.0 * (flow - minimum) / (optimal_low - minimum)
    if flow <= optimal_high:
        return 100.0
    return 100.0 * (maximum - flow) / (maximum - optimal_high)


def _same_kma_window(
    rows: tuple[Any, ...],
    *,
    snapshot: Any,
    at: datetime,
) -> bool:
    if snapshot.valid_from is None or snapshot.valid_until is None:
        return False
    if snapshot.valid_until < snapshot.valid_from or snapshot.fetched_at > at:
        return False
    modes = {row.mode for row in rows}
    stations = {row.station_id for row in rows}
    scopes = {row.spatial_scope for row in rows}
    if len(modes) != 1 or len(stations) != 1 or len(scopes) != 1:
        return False
    if not next(iter(stations)) or scopes != {snapshot.spatial_scope}:
        return False
    if next(iter(modes)) not in {
        MetricMode.OBSERVED.value,
        MetricMode.FORECAST.value,
    }:
        return False
    for row in rows:
        if (
            row.state != "valid"
            or _canonical_source(row.source) != "KMA"
            or row.valid_from != snapshot.valid_from
            or row.valid_until != snapshot.valid_until
            or row.fetched_at > at
            or row.observed_at > row.fetched_at
            or not _strict_public_url(row.source_url)
            or not _valid_confidence(row.confidence)
        ):
            return False
        if row.mode != MetricMode.FORECAST.value and row.observed_at > at:
            return False
    return True


def _verified_facility_catalog(spot: Any, *, at: datetime) -> bool:
    confidence = getattr(spot, "catalog_confidence", None)
    verified_at = getattr(spot, "catalog_verified_at", None)
    try:
        normalized_confidence = float(confidence)
    except (TypeError, ValueError):
        return False
    return bool(
        getattr(spot, "catalog_verification", "") == "verified"
        and math.isfinite(normalized_confidence)
        and 0.8 <= normalized_confidence <= 1.0
        and isinstance(getattr(spot, "catalog_source", None), str)
        and spot.catalog_source.strip()
        and _strict_public_url(getattr(spot, "catalog_source_url", ""))
        and isinstance(verified_at, datetime)
        and verified_at.tzinfo is not None
        and verified_at.utcoffset() is not None
        and verified_at <= at
    )


def _official_metric_is_current(
    row: Any,
    *,
    at: datetime,
    max_age: timedelta,
    allowed_sources: frozenset[str],
    required_scope: str,
    required_unit: str | None,
) -> bool:
    source = _canonical_source(row.source)
    provider = _canonical_source(row.snapshot.provider)
    if source not in allowed_sources or provider != source:
        return False
    if (
        row.snapshot.state != "live"
        or row.state != "valid"
        or row.mode != MetricMode.OBSERVED.value
        or row.spatial_scope != required_scope
        or row.snapshot.spatial_scope != required_scope
        or not row.station_id
        or not _strict_public_url(row.source_url)
        or not _valid_confidence(row.confidence)
        or row.fetched_at > at
        or row.observed_at > at
        or row.observed_at > row.fetched_at
    ):
        return False
    if required_unit is not None and row.unit != required_unit:
        return False
    valid_from = row.valid_from or row.observed_at
    try:
        valid_until = _effective_expiry(row, max_age=max_age)
    except ValueError:
        return False
    return valid_from <= at <= valid_until


def _effective_expiry(row: Any, *, max_age: timedelta) -> datetime:
    expiries = [row.observed_at + max_age]
    if row.valid_until is not None:
        expiries.append(row.valid_until)
    expiry = min(expiries)
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError("metric expiry must be timezone-aware")
    return expiry


def _operation_status(value: Any) -> str | None:
    canonical = str(value).strip().lower().replace(" ", "_")
    if canonical in _OPEN_OPERATION_VALUES:
        return "open"
    if canonical in _CLOSED_OPERATION_VALUES:
        return "closed"
    return None


def _number(row: Any, *, unit: str) -> float | None:
    if row.unit != unit or isinstance(row.value, bool):
        return None
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _valid_confidence(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(normalized) and 0 <= normalized <= 1


def _derived_metric(
    *,
    name: str,
    value: float,
    unit: str,
    observed_at: datetime,
    fetched_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    mode: MetricMode,
    confidence: float,
    source_url: str,
    station_id: str,
    spatial_scope: str,
) -> Metric:
    return Metric(
        name=name,
        value=float(value),
        unit=unit,
        source=DERIVED_PROVIDER,
        source_url=source_url,
        station_id=station_id,
        spatial_scope=spatial_scope,
        observed_at=observed_at,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        mode=mode,
        confidence=confidence,
        state=MetricState.VALID,
    )


def _lineage(
    source_ids_by_metric: dict[str, Iterable[int]],
) -> tuple[MetricLineageInput, ...]:
    return tuple(
        MetricLineageInput(
            derived_metric_name=name,
            source_metric_id=source_id,
            relation="selected",
            priority=_LINEAGE_PRIORITY,
        )
        for name in sorted(source_ids_by_metric)
        for source_id in sorted(set(source_ids_by_metric[name]))
    )


def _common_public_source_url(rows: tuple[Any, ...]) -> str:
    urls = {
        public_https_url(row.source_url)
        for row in rows
        if _strict_public_url(row.source_url)
    }
    urls.discard("")
    return next(iter(urls)) if len(urls) == 1 else ""


def _strict_public_url(value: Any) -> bool:
    if not isinstance(value, str) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
    except (TypeError, ValueError):
        return False
    return bool(
        public_https_url(value)
        and not parsed.query
        and not parsed.fragment
    )


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metric_identity(row: Any) -> dict[str, Any]:
    return {
        "id": row.pk,
        "name": row.name,
        "value": row.value,
        "unit": row.unit,
        "source": row.source,
        "source_url": row.source_url,
        "station_id": row.station_id,
        "scope": row.spatial_scope,
        "mode": row.mode,
        "state": row.state,
        "confidence": float(row.confidence),
        "observed_at": row.observed_at.isoformat(),
        "fetched_at": row.fetched_at.isoformat(),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
    }


def _canonical_source(value: Any) -> str:
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
