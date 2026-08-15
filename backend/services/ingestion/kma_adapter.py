"""Normalize KMA village-weather values with explicit temporal provenance.

KMA categories describe grid weather observations and forecasts. They do not
prove that a water activity is open, patrolled, free from marine warnings, or
clear of lightning for 30 minutes. This adapter therefore preserves weather
values only and never emits a Water Index safety-clearance signal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable
from urllib.parse import urljoin

from services.providers.kma import KmaClient, WeatherValue
from services.water_index import Metric, MetricMode, MetricState, ObservationSet


INGESTION_VERSION = "kma-adapter-v1"
OBSERVATION_VALIDITY = timedelta(minutes=70)
FORECAST_VALIDITY = timedelta(hours=1)


class KmaAdapterError(ValueError):
    """KMA values cannot be normalized without losing temporal integrity."""


@dataclass(frozen=True, slots=True)
class AdaptedKmaObservation:
    provider: str
    endpoint: str
    source_url: str
    provider_record_id: str
    state: str
    ingestion_version: str
    source_observed_at: datetime | None
    fetched_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    evaluation_at: datetime
    spatial_scope: str
    observations: ObservationSet


_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "T1H": ("air_temperature_c", "degC"),
    "TMP": ("air_temperature_c", "degC"),
    "TMN": ("minimum_air_temperature_c", "degC"),
    "TMX": ("maximum_air_temperature_c", "degC"),
    "RN1": ("precipitation_1h_mm", "mm"),
    "PCP": ("precipitation_amount_text", "provider_text"),
    "SNO": ("snow_amount_text", "provider_text"),
    "WSD": ("wind_speed_ms", "m/s"),
    "UUU": ("east_west_wind_ms", "m/s"),
    "VVV": ("north_south_wind_ms", "m/s"),
    "VEC": ("wind_direction_degrees", "degree"),
    "REH": ("relative_humidity_pct", "percent"),
    "POP": ("precipitation_probability_pct", "percent"),
    "WAV": ("wave_height_m", "m"),
    "PTY": ("precipitation_type_code", "provider_code"),
    "SKY": ("sky_condition_code", "provider_code"),
    # LGT is a provider category code, not proof that the 30-minute lightning
    # clearance rule has been satisfied.
    "LGT": ("lightning_category_code", "provider_code"),
}


def adapt_weather_values(
    records: Iterable[WeatherValue],
    *,
    fetched_at: datetime,
    endpoint: str,
    forecast: bool,
) -> tuple[AdaptedKmaObservation, ...]:
    """Group typed KMA values by issue/valid time and normalize each group."""

    _require_aware(fetched_at, "fetched_at")
    grouped: dict[
        tuple[datetime, datetime, int, int], list[WeatherValue]
    ] = {}
    for record in records:
        _validate_record(record, fetched_at=fetched_at, forecast=forecast)
        key = (
            record.issued_at,
            record.valid_at,
            record.grid_x,
            record.grid_y,
        )
        grouped.setdefault(key, []).append(record)

    return tuple(
        _adapt_group(
            values,
            fetched_at=fetched_at,
            endpoint=endpoint,
            forecast=forecast,
        )
        for _, values in sorted(grouped.items(), key=lambda item: item[0])
    )


def _adapt_group(
    records: list[WeatherValue],
    *,
    fetched_at: datetime,
    endpoint: str,
    forecast: bool,
) -> AdaptedKmaObservation:
    first = records[0]
    mode = MetricMode.FORECAST if forecast else MetricMode.OBSERVED
    valid_from = first.valid_at
    valid_until = valid_from + (
        FORECAST_VALIDITY if forecast else OBSERVATION_VALIDITY
    )
    scope = f"kma-grid:{first.grid_x},{first.grid_y}"
    source_url = _endpoint_url(endpoint)
    observed_at = first.issued_at if forecast else first.valid_at
    metrics: list[Metric] = []
    seen_names: set[str] = set()
    for record in sorted(records, key=lambda item: item.category):
        mapped = _CATEGORY_MAP.get(record.category.upper())
        if mapped is None or record.value is None:
            continue
        name, unit = mapped
        if name in seen_names:
            raise KmaAdapterError(f"duplicate canonical KMA metric: {name}")
        seen_names.add(name)
        metrics.append(
            Metric(
                name=name,
                value=_metric_value(record.value),
                unit=unit,
                source="KMA",
                source_url=KmaClient.SOURCE_URL,
                station_id=f"{record.grid_x},{record.grid_y}",
                spatial_scope=scope,
                observed_at=observed_at,
                fetched_at=fetched_at,
                valid_from=valid_from,
                valid_until=valid_until,
                mode=mode,
                state=MetricState.VALID,
            )
        )

    if not metrics:
        state = "error"
    elif fetched_at > valid_until:
        state = "stale"
    else:
        state = "live"
    if valid_from <= fetched_at <= valid_until:
        evaluation_at = fetched_at
    elif fetched_at < valid_from:
        evaluation_at = valid_from
    else:
        evaluation_at = fetched_at

    return AdaptedKmaObservation(
        provider="KMA",
        endpoint=endpoint,
        source_url=source_url,
        provider_record_id=_record_id(endpoint, records),
        state=state,
        ingestion_version=INGESTION_VERSION,
        source_observed_at=None if forecast else observed_at,
        fetched_at=fetched_at,
        valid_from=valid_from,
        valid_until=valid_until,
        evaluation_at=evaluation_at,
        spatial_scope=scope,
        observations=ObservationSet.from_metrics(*metrics),
    )


def _validate_record(
    record: WeatherValue, *, fetched_at: datetime, forecast: bool
) -> None:
    _require_aware(record.issued_at, "issued_at")
    _require_aware(record.valid_at, "valid_at")
    if record.issued_at > fetched_at:
        raise KmaAdapterError("KMA issue time is later than fetched_at")
    if not forecast and record.valid_at > fetched_at:
        raise KmaAdapterError("KMA observation time is later than fetched_at")
    if forecast and record.valid_at < record.issued_at:
        raise KmaAdapterError("KMA forecast validity precedes its issue time")
    if not 1 <= record.grid_x <= 1000 or not 1 <= record.grid_y <= 1000:
        raise KmaAdapterError("KMA grid coordinate is out of bounds")


def _record_id(endpoint: str, records: list[WeatherValue]) -> str:
    payload = [
        {
            "category": record.category,
            "value": str(record.value) if record.value is not None else None,
            "unit": record.unit,
            "issued_at": record.issued_at.isoformat(),
            "valid_at": record.valid_at.isoformat(),
            "grid_x": record.grid_x,
            "grid_y": record.grid_y,
        }
        for record in sorted(records, key=lambda item: item.category)
    ]
    encoded = json.dumps(
        {"endpoint": endpoint, "records": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _endpoint_url(endpoint: str) -> str:
    return urljoin(f"{KmaClient.BASE_URL}/", endpoint.lstrip("/"))


def _metric_value(value: Decimal | str) -> float | str:
    return float(value) if isinstance(value, Decimal) else value


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise KmaAdapterError(f"{field_name} must be timezone-aware")
