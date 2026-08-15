"""Normalize typed KHOA records without inventing unavailable safety evidence.

KHOA's activity endpoints provide activity grades and selected environmental
forecast values. They do not, by themselves, prove that entry is permitted,
water quality passed, a lifeguard is present, or no warning is active. This
adapter consequently emits only fields present in the typed provider records.
The Water Index engine is responsible for failing closed on the absent safety
requirements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable, Iterable
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from services.providers.khoa import (
    BeachForecast,
    KhoaClient,
    MudflatForecast,
    RipCurrentForecast,
    SurfForecast,
)
from services.water_index import Activity, Metric, MetricMode, MetricState, ObservationSet


KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
INGESTION_VERSION = "khoa-adapter-v2"
TIDE_WINDOW_START_METRIC = "official_tide_window_start"
TIDE_WINDOW_END_METRIC = "official_tide_window_end"


class KhoaAdapterError(ValueError):
    """A typed KHOA record cannot be represented without losing provenance."""


@dataclass(frozen=True, slots=True)
class AdaptedKhoaObservation:
    """One provider record plus its canonical Water Index observations."""

    provider: str
    endpoint: str
    source_url: str
    provider_record_id: str
    state: str
    ingestion_version: str
    activity: Activity
    place_name: str | None
    latitude: float | None
    longitude: float | None
    spatial_scope: str
    source_observed_at: datetime | None
    fetched_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    evaluation_at: datetime
    observations: ObservationSet


def adapt_beach_forecast(
    record: BeachForecast,
    *,
    fetched_at: datetime,
    endpoint: str = KhoaClient.BEACH_ENDPOINT,
) -> AdaptedKhoaObservation:
    """Adapt a KHOA beach activity forecast for the swim index."""

    fetched_at = _require_aware_fetched_at(fetched_at)
    valid_from, valid_until = _forecast_period(
        record.forecast_date, record.forecast_time_code
    )
    scope = _spatial_scope(record.place_name, record.latitude, record.longitude)
    source_url = _source_url(endpoint)
    metrics: tuple[Metric, ...] = ()
    if valid_from is not None and valid_until is not None:
        metric = _metric_factory(
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            scope=scope,
            source_url=source_url,
            mode=MetricMode.FORECAST,
            state=MetricState.VALID,
        )
        metrics = _present_metrics(
            (
                metric("official_activity_grade", record.official_grade, "official_grade"),
                metric("official_activity_score", record.score, "provider_points"),
                metric("maximum_wave_height_m", record.maximum_wave_height, "m"),
                metric("water_temperature_c", record.average_water_temperature, "degC"),
                metric("air_temperature_c", record.average_air_temperature, "degC"),
                metric("maximum_wind_speed_ms", record.maximum_wind_speed, "m/s"),
            )
        )
    return _adapted(
        kind="beach",
        record=record,
        endpoint=endpoint,
        activity=Activity.SWIM,
        place_name=record.place_name,
        latitude=record.latitude,
        longitude=record.longitude,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        metrics=metrics,
        state=_forecast_snapshot_state(
            fetched_at, valid_from, valid_until, has_metrics=bool(metrics)
        ),
    )


def adapt_surf_forecast(
    record: SurfForecast,
    *,
    fetched_at: datetime,
    endpoint: str = KhoaClient.SURF_ENDPOINT,
) -> AdaptedKhoaObservation:
    """Adapt a KHOA surfing activity forecast."""

    fetched_at = _require_aware_fetched_at(fetched_at)
    valid_from, valid_until = _forecast_period(
        record.forecast_date, record.forecast_time_code
    )
    scope = _spatial_scope(record.place_name, record.latitude, record.longitude)
    source_url = _source_url(endpoint)
    metrics: tuple[Metric, ...] = ()
    if valid_from is not None and valid_until is not None:
        metric = _metric_factory(
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            scope=scope,
            source_url=source_url,
            mode=MetricMode.FORECAST,
            state=MetricState.VALID,
        )
        metrics = _present_metrics(
            (
                metric("official_activity_grade", record.official_grade, "official_grade"),
                metric("official_activity_score", record.score, "provider_points"),
                metric("official_grade_detail", record.grade_detail, "text"),
                metric("wave_height_m", record.average_wave_height, "m"),
                metric("wave_period_seconds", record.average_wave_period, "s"),
                metric("wind_speed_ms", record.average_wind_speed, "m/s"),
                metric("water_temperature_c", record.average_water_temperature, "degC"),
            )
        )
    return _adapted(
        kind="surf",
        record=record,
        endpoint=endpoint,
        activity=Activity.SURF,
        place_name=record.place_name,
        latitude=record.latitude,
        longitude=record.longitude,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        metrics=metrics,
        state=_forecast_snapshot_state(
            fetched_at, valid_from, valid_until, has_metrics=bool(metrics)
        ),
    )


def adapt_mudflat_forecast(
    record: MudflatForecast,
    *,
    fetched_at: datetime,
    endpoint: str = KhoaClient.MUDFLAT_ENDPOINT,
) -> AdaptedKhoaObservation:
    """Adapt an official mudflat window and forecast.

    ``tide_window_open`` is derived only when both official experience times and
    the forecast date are parseable. No access, warning, fog, or route-clear
    signal is inferred from a weather description.
    """

    fetched_at = _require_aware_fetched_at(fetched_at)
    valid_from, valid_until = _mudflat_period(record)
    scope = _spatial_scope(record.place_name, record.latitude, record.longitude)
    source_url = _source_url(endpoint)
    metrics: list[Metric | None] = []
    if valid_from is not None and valid_until is not None:
        metric = _metric_factory(
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            scope=scope,
            source_url=source_url,
            mode=MetricMode.FORECAST,
            state=MetricState.VALID,
        )
        metrics.extend(
            (
                metric("official_activity_grade", record.official_grade, "official_grade"),
                metric("official_activity_score", record.score, "provider_points"),
                metric("weather_description", record.weather, "text"),
                metric("maximum_air_temperature_c", record.maximum_air_temperature, "degC"),
                metric("minimum_air_temperature_c", record.minimum_air_temperature, "degC"),
                metric("maximum_wind_speed_ms", record.maximum_wind_speed, "m/s"),
                metric("minimum_wind_speed_ms", record.minimum_wind_speed, "m/s"),
                metric(TIDE_WINDOW_START_METRIC, valid_from.isoformat(), "iso8601"),
                metric(TIDE_WINDOW_END_METRIC, valid_until.isoformat(), "iso8601"),
            )
        )
        metrics.append(
            _tide_window_status_metric(
                fetched_at=fetched_at,
                valid_from=valid_from,
                valid_until=valid_until,
                scope=scope,
                source_url=source_url,
            )
        )
    return _adapted(
        kind="mudflat",
        record=record,
        endpoint=endpoint,
        activity=Activity.MUDFLAT,
        place_name=record.place_name,
        latitude=record.latitude,
        longitude=record.longitude,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        metrics=_present_metrics(metrics),
        evaluation_at=fetched_at,
        state=_forecast_snapshot_state(
            fetched_at,
            valid_from,
            valid_until,
            has_metrics=bool(_present_metrics(metrics)),
        ),
    )


def adapt_rip_current_forecast(
    record: RipCurrentForecast,
    *,
    fetched_at: datetime,
    endpoint: str = KhoaClient.RIP_CURRENT_ENDPOINT,
) -> AdaptedKhoaObservation:
    """Adapt an observed KHOA rip-current record without clearing other gates."""

    fetched_at = _require_aware_fetched_at(fetched_at)
    source_observed_at = _source_datetime(record.observed_at)
    if source_observed_at is not None and source_observed_at > fetched_at:
        raise KhoaAdapterError("KHOA observed timestamp is later than the fetch timestamp")
    observed_at = source_observed_at or fetched_at
    valid_until = (
        source_observed_at + timedelta(minutes=20)
        if source_observed_at is not None
        else None
    )
    state = MetricState.VALID if source_observed_at is not None else MetricState.INVALID
    scope = _spatial_scope(record.beach_name, record.latitude, record.longitude)
    source_url = _source_url(endpoint)
    metric = _metric_factory(
        fetched_at=fetched_at,
        valid_from=source_observed_at,
        valid_until=valid_until,
        scope=scope,
        source_url=source_url,
        mode=MetricMode.OBSERVED,
        state=state,
        observed_at=observed_at,
        station_id=record.beach_code or "",
    )
    rip_value: Decimal | str | None = record.index_value
    if rip_value is None:
        rip_value = record.official_index
    metrics = _present_metrics(
        (
            metric("rip_current_risk", rip_value, "official_index"),
            metric("rip_current_message", record.risk_message, "text"),
            metric("wave_height_m", record.wave_height_m, "m"),
            metric("wave_period_seconds", record.wave_period_seconds, "s"),
            metric("water_temperature_c", record.water_temperature_celsius, "degC"),
            metric("air_temperature_c", record.air_temperature_celsius, "degC"),
            metric("wind_direction", record.wind_direction, "text"),
            metric("wind_speed_ms", record.wind_speed_mps, "m/s"),
        )
    )
    return _adapted(
        kind="rip-current",
        record=record,
        endpoint=endpoint,
        activity=Activity.SWIM,
        place_name=record.beach_name,
        latitude=record.latitude,
        longitude=record.longitude,
        fetched_at=fetched_at,
        valid_from=source_observed_at,
        valid_until=valid_until,
        metrics=metrics,
        source_observed_at=source_observed_at,
        state=_observed_snapshot_state(
            fetched_at,
            source_observed_at,
            has_metrics=bool(metrics),
            maximum_age=timedelta(minutes=20),
        ),
    )


def _adapted(
    *,
    kind: str,
    record: object,
    endpoint: str,
    activity: Activity,
    place_name: str | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
    fetched_at: datetime,
    valid_from: datetime | None,
    valid_until: datetime | None,
    metrics: tuple[Metric, ...],
    source_observed_at: datetime | None = None,
    evaluation_at: datetime | None = None,
    state: str = "live",
) -> AdaptedKhoaObservation:
    scope = _spatial_scope(place_name, latitude, longitude)
    evaluation_at = evaluation_at or _evaluation_time(
        fetched_at,
        valid_from,
        valid_until,
    )
    return AdaptedKhoaObservation(
        provider="KHOA",
        endpoint=endpoint,
        source_url=_source_url(endpoint),
        provider_record_id=_record_id(kind, endpoint, record),
        state=state,
        ingestion_version=INGESTION_VERSION,
        activity=activity,
        place_name=place_name,
        latitude=_float_or_none(latitude),
        longitude=_float_or_none(longitude),
        spatial_scope=scope,
        source_observed_at=source_observed_at,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        evaluation_at=evaluation_at,
        observations=ObservationSet.from_metrics(*metrics),
    )


def _tide_window_status_metric(
    *,
    fetched_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    scope: str,
    source_url: str,
) -> Metric | None:
    """Evaluate one explicit KHOA window without extending it to another date."""

    local_date = fetched_at.astimezone(valid_from.tzinfo).date()
    if not valid_from.date() <= local_date <= valid_until.date():
        return None
    is_open = valid_from <= fetched_at <= valid_until
    metric_valid_from = valid_from if is_open else fetched_at
    metric_valid_until = valid_until if is_open else fetched_at
    return Metric(
        name="tide_window_open",
        value=is_open,
        unit="boolean",
        source="KHOA",
        source_url=source_url,
        spatial_scope=scope,
        observed_at=fetched_at,
        fetched_at=fetched_at,
        valid_from=metric_valid_from,
        valid_until=metric_valid_until,
        mode=MetricMode.FORECAST,
        state=MetricState.VALID,
        confidence=1.0,
    )


def _metric_factory(
    *,
    fetched_at: datetime,
    valid_from: datetime | None,
    valid_until: datetime | None,
    scope: str,
    source_url: str,
    mode: MetricMode,
    state: MetricState,
    observed_at: datetime | None = None,
    station_id: str = "",
) -> Callable[[str, Any, str], Metric | None]:
    evidence_time = observed_at or fetched_at

    def build(name: str, value: Any, unit: str) -> Metric | None:
        normalized = _metric_value(value)
        if normalized is None:
            return None
        return Metric(
            name=name,
            value=normalized,
            unit=unit,
            source="KHOA",
            source_url=source_url,
            station_id=station_id,
            spatial_scope=scope,
            observed_at=evidence_time,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            mode=mode,
            state=state,
            confidence=1.0,
        )

    return build


def _present_metrics(values: Iterable[Metric | None]) -> tuple[Metric, ...]:
    return tuple(metric for metric in values if metric is not None)


def _metric_value(value: Any) -> float | str | bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    return text or None


def _require_aware_fetched_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise KhoaAdapterError("fetched_at must be timezone-aware")
    return value


def _source_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=KOREA_TIME_ZONE)
    return value.astimezone(KOREA_TIME_ZONE)


def _forecast_period(
    forecast_date: date | None, forecast_time_code: str | None
) -> tuple[datetime | None, datetime | None]:
    if forecast_date is None:
        return None, None
    code = (forecast_time_code or "").strip().lower().replace(" ", "")
    if code in {"오전", "am", "a", "1", "morning"}:
        start, end = time.min, time(11, 59, 59, 999999)
    elif code in {"오후", "pm", "p", "2", "afternoon"}:
        start, end = time(12), time.max
    else:
        return None, None
    return (
        datetime.combine(forecast_date, start, tzinfo=KOREA_TIME_ZONE),
        datetime.combine(forecast_date, end, tzinfo=KOREA_TIME_ZONE),
    )


def _mudflat_period(
    record: MudflatForecast,
) -> tuple[datetime | None, datetime | None]:
    if record.forecast_date is None:
        return None, None
    start_time = _parse_clock_time(record.experience_start_time)
    end_time = _parse_clock_time(record.experience_end_time)
    if start_time is None or end_time is None:
        return None, None
    start = datetime.combine(record.forecast_date, start_time, tzinfo=KOREA_TIME_ZONE)
    end = datetime.combine(record.forecast_date, end_time, tzinfo=KOREA_TIME_ZONE)
    if end == start:
        return None, None
    if end < start:
        end += timedelta(days=1)
    return start, end


def _parse_clock_time(value: str | None) -> time | None:
    if value is None:
        return None
    text = value.strip()
    for format_string in ("%H:%M:%S", "%H:%M", "%H%M%S", "%H%M"):
        try:
            return datetime.strptime(text, format_string).time()
        except ValueError:
            continue
    return None


def _evaluation_time(
    fetched_at: datetime,
    valid_from: datetime | None,
    valid_until: datetime | None,
) -> datetime:
    if valid_from is not None and fetched_at < valid_from:
        return valid_from
    if valid_until is not None and fetched_at > valid_until:
        return fetched_at
    return fetched_at


def _forecast_snapshot_state(
    fetched_at: datetime,
    valid_from: datetime | None,
    valid_until: datetime | None,
    *,
    has_metrics: bool,
) -> str:
    if valid_from is None or valid_until is None or not has_metrics:
        return "error"
    if fetched_at > valid_until:
        return "stale"
    return "live"


def _observed_snapshot_state(
    fetched_at: datetime,
    observed_at: datetime | None,
    *,
    has_metrics: bool,
    maximum_age: timedelta,
) -> str:
    if observed_at is None or not has_metrics:
        return "error"
    if fetched_at - observed_at > maximum_age:
        return "stale"
    return "live"


def _source_url(endpoint: str) -> str:
    if not endpoint.startswith("/"):
        raise KhoaAdapterError("KHOA endpoint must be an absolute-path reference")
    return urljoin(KhoaClient.BASE_URL.rstrip("/") + "/", endpoint.lstrip("/"))


def _spatial_scope(
    place_name: str | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> str:
    parts: list[str] = []
    if place_name and place_name.strip():
        parts.append(f"place:{place_name.strip()}")
    if latitude is not None and longitude is not None:
        parts.append(f"point:{latitude},{longitude}")
    return ";".join(parts) or "provider-record:unspecified"


def _record_id(kind: str, endpoint: str, record: object) -> str:
    payload = {
        "endpoint": endpoint,
        "record": asdict(record),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:40]
    return f"{kind}:{digest}"


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported provider-record value: {type(value).__name__}")


def _float_or_none(value: Decimal | None) -> float | None:
    return float(value) if value is not None and value.is_finite() else None
