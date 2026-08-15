"""Typed boundary for KMA's village forecast service.

Only fields documented by the Public Data Portal contract cross this boundary.
The service key, request URL, raw response, and provider message never become
part of returned records or raised exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .base import (
    JsonProviderClient,
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderResponseError,
    ProviderResult,
)


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class WeatherValue:
    """One KMA category value at one grid point and time."""

    category: str
    value: Decimal | str | None
    unit: str
    issued_at: datetime
    valid_at: datetime
    grid_x: int
    grid_y: int


@dataclass(frozen=True, slots=True)
class KmaGrid:
    x: int
    y: int


def latlon_to_grid(latitude: float | Decimal, longitude: float | Decimal) -> KmaGrid:
    """Convert WGS84 coordinates to KMA's 5 km Lambert grid.

    Constants are the ones published with the village-forecast API guide. The
    conversion chooses a request cell; it is not evidence that the grid value
    directly represents an offshore or hyper-local beach condition.
    """

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("latitude and longitude must be finite numbers") from None
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("latitude and longitude must be finite numbers")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("latitude or longitude is outside geographic bounds")

    earth_radius_km = 6371.00877
    grid_spacing_km = 5.0
    standard_latitude_1 = math.radians(30.0)
    standard_latitude_2 = math.radians(60.0)
    origin_longitude = math.radians(126.0)
    origin_latitude = math.radians(38.0)
    false_easting = 43.0
    false_northing = 136.0

    scaled_radius = earth_radius_km / grid_spacing_km
    cone = math.tan(math.pi / 4 + standard_latitude_2 / 2) / math.tan(
        math.pi / 4 + standard_latitude_1 / 2
    )
    cone = math.log(
        math.cos(standard_latitude_1) / math.cos(standard_latitude_2)
    ) / math.log(cone)
    scale = math.tan(math.pi / 4 + standard_latitude_1 / 2)
    scale = math.pow(scale, cone) * math.cos(standard_latitude_1) / cone
    origin_radius = math.tan(math.pi / 4 + origin_latitude / 2)
    origin_radius = scaled_radius * scale / math.pow(origin_radius, cone)
    point_radius = math.tan(math.pi / 4 + math.radians(lat) / 2)
    point_radius = scaled_radius * scale / math.pow(point_radius, cone)
    theta = math.radians(lon) - origin_longitude
    if theta > math.pi:
        theta -= 2 * math.pi
    if theta < -math.pi:
        theta += 2 * math.pi
    theta *= cone
    return KmaGrid(
        x=math.floor(point_radius * math.sin(theta) + false_easting + 0.5),
        y=math.floor(
            origin_radius - point_radius * math.cos(theta) + false_northing + 0.5
        ),
    )


class KmaClient(JsonProviderClient):
    """Server-side client for KMA nowcast and short-term forecast values."""

    BASE_URL = "https://apis.data.go.kr"
    NOWCAST_ENDPOINT = "/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    ULTRA_SHORT_FORECAST_ENDPOINT = (
        "/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
    )
    SHORT_FORECAST_ENDPOINT = "/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    SOURCE_URL = "https://www.data.go.kr/data/15084084/openapi.do"

    _NUMERIC_CATEGORIES = frozenset(
        {
            "T1H",
            "RN1",
            "UUU",
            "VVV",
            "REH",
            "VEC",
            "WSD",
            "TMP",
            "POP",
            "WAV",
            "TMN",
            "TMX",
        }
    )
    _UNITS = {
        "T1H": "celsius",
        "TMP": "celsius",
        "TMN": "celsius",
        "TMX": "celsius",
        "RN1": "millimetre",
        "PCP": "provider_text",
        "SNO": "provider_text",
        "UUU": "metre_per_second",
        "VVV": "metre_per_second",
        "WSD": "metre_per_second",
        "VEC": "degree",
        "REH": "percent",
        "POP": "percent",
        "WAV": "metre",
        "PTY": "provider_code",
        "SKY": "provider_code",
        "LGT": "provider_code",
    }

    def __init__(
        self,
        service_key: str,
        *,
        session: Any | None = None,
        timeout: tuple[float, float] = (3.05, 10.0),
        max_retries: int = 2,
        backoff_factor: float = 0.25,
        sleeper: Any | None = None,
    ) -> None:
        if not isinstance(service_key, str) or not service_key.strip():
            raise ProviderConfigurationError("KMA service key is required")
        kwargs: dict[str, Any] = {
            "provider": "KMA",
            "base_url": self.BASE_URL,
            "session": session,
            "timeout": timeout,
            "max_retries": max_retries,
            "backoff_factor": backoff_factor,
        }
        if sleeper is not None:
            kwargs["sleeper"] = sleeper
        super().__init__(**kwargs)
        self.__service_key = service_key.strip()

    def fetch_nowcast(
        self, *, issued_at: datetime, grid_x: int, grid_y: int
    ) -> ProviderResult[WeatherValue]:
        return self._fetch(
            self.NOWCAST_ENDPOINT,
            issued_at=issued_at,
            grid_x=grid_x,
            grid_y=grid_y,
            value_field="obsrValue",
            forecast=False,
        )

    def fetch_ultra_short_forecast(
        self, *, issued_at: datetime, grid_x: int, grid_y: int
    ) -> ProviderResult[WeatherValue]:
        return self._fetch(
            self.ULTRA_SHORT_FORECAST_ENDPOINT,
            issued_at=issued_at,
            grid_x=grid_x,
            grid_y=grid_y,
            value_field="fcstValue",
            forecast=True,
        )

    def fetch_short_forecast(
        self, *, issued_at: datetime, grid_x: int, grid_y: int
    ) -> ProviderResult[WeatherValue]:
        return self._fetch(
            self.SHORT_FORECAST_ENDPOINT,
            issued_at=issued_at,
            grid_x=grid_x,
            grid_y=grid_y,
            value_field="fcstValue",
            forecast=True,
        )

    def _fetch(
        self,
        endpoint: str,
        *,
        issued_at: datetime,
        grid_x: int,
        grid_y: int,
        value_field: str,
        forecast: bool,
    ) -> ProviderResult[WeatherValue]:
        # KMA's request contract is minute-granular. Normalize caller seconds
        # rather than later accepting a response for a different issue slot.
        issued_kst = _aware_kst(issued_at).replace(second=0, microsecond=0)
        normalized_x = _grid_coordinate(grid_x, "grid_x")
        normalized_y = _grid_coordinate(grid_y, "grid_y")
        payload = self._get_json(
            endpoint,
            {
                "serviceKey": self.__service_key,
                "pageNo": 1,
                "numOfRows": 1000,
                "dataType": "JSON",
                "base_date": issued_kst.strftime("%Y%m%d"),
                "base_time": issued_kst.strftime("%H%M"),
                "nx": normalized_x,
                "ny": normalized_y,
            },
        )
        body = self._validated_body(payload)
        items = _normalize_items(body.get("items"))
        records = tuple(
            self._parse_value(
                item,
                requested_issue=issued_kst,
                requested_x=normalized_x,
                requested_y=normalized_y,
                value_field=value_field,
                forecast=forecast,
            )
            for item in items
        )
        total = _integer(body.get("totalCount"))
        if total is not None and total >= 0 and len(records) < total:
            raise ProviderPayloadError(
                "KMA", "response exceeds the bounded one-page request"
            )
        return ProviderResult(
            provider="KMA",
            endpoint=endpoint,
            records=records,
            reported_total_count=max(total, 0) if total is not None else None,
        )

    @staticmethod
    def _validated_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = payload.get("response", payload)
        if not isinstance(envelope, Mapping):
            raise ProviderPayloadError("KMA", "response envelope is not an object")
        header = envelope.get("header")
        if not isinstance(header, Mapping):
            raise ProviderPayloadError("KMA", "response header is missing")
        result_code = _text(header.get("resultCode"))
        if result_code is None:
            raise ProviderPayloadError("KMA", "resultCode is missing")
        if result_code != "00":
            raise ProviderResponseError("KMA", result_code)
        body = envelope.get("body")
        if not isinstance(body, Mapping):
            raise ProviderPayloadError("KMA", "response body is missing")
        return body

    @classmethod
    def _parse_value(
        cls,
        item: Mapping[str, Any],
        *,
        requested_issue: datetime,
        requested_x: int,
        requested_y: int,
        value_field: str,
        forecast: bool,
    ) -> WeatherValue:
        category = _text(item.get("category"))
        if category is None:
            raise ProviderPayloadError("KMA", "weather category is missing")
        category = category.upper()
        base_date = _text(item.get("baseDate"))
        base_time = _text(item.get("baseTime"))
        if (base_date is None) != (base_time is None):
            raise ProviderPayloadError("KMA", "response issue time is incomplete")
        issued_at = _provider_datetime(base_date, base_time)
        if base_date is not None:
            if issued_at is None:
                raise ProviderPayloadError("KMA", "response issue time is invalid")
            if issued_at != requested_issue:
                raise ProviderPayloadError(
                    "KMA", "response issue time does not match the request"
                )
        else:
            issued_at = requested_issue
        if forecast:
            valid_at = _provider_datetime(
                item.get("fcstDate"), item.get("fcstTime")
            )
            if valid_at is None:
                raise ProviderPayloadError("KMA", "forecast valid time is missing")
        else:
            valid_at = issued_at

        raw_x = item.get("nx")
        raw_y = item.get("ny")
        x = _integer(raw_x)
        y = _integer(raw_y)
        if raw_x not in (None, "") and x is None:
            raise ProviderPayloadError("KMA", "response grid x is invalid")
        if raw_y not in (None, "") and y is None:
            raise ProviderPayloadError("KMA", "response grid y is invalid")
        if x is not None and x != requested_x:
            raise ProviderPayloadError(
                "KMA", "response grid x does not match the request"
            )
        if y is not None and y != requested_y:
            raise ProviderPayloadError(
                "KMA", "response grid y does not match the request"
            )
        x = requested_x if x is None else x
        y = requested_y if y is None else y
        raw_value = _text(item.get(value_field))
        value: Decimal | str | None
        if category in cls._NUMERIC_CATEGORIES:
            value = _decimal(raw_value)
        else:
            value = raw_value
        return WeatherValue(
            category=category,
            value=value,
            unit=cls._UNITS.get(category, "provider_value"),
            issued_at=issued_at,
            valid_at=valid_at,
            grid_x=x,
            grid_y=y,
        )


def _aware_kst(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("issued_at must be timezone-aware")
    return value.astimezone(KST)


def _grid_coordinate(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValueError(f"{name} must be an integer between 1 and 1000")
    return value


def _normalize_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, Mapping):
        value = value.get("item")
    if value in (None, ""):
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(value)
    raise ProviderPayloadError("KMA", "items.item is neither an object nor a list")


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    normalized = str(value).strip()
    return normalized or None


def _decimal(value: Any) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _integer(value: Any) -> int | None:
    parsed = _decimal(value)
    if parsed is None or parsed != parsed.to_integral_value():
        return None
    try:
        return int(parsed)
    except (OverflowError, ValueError):
        return None


def _provider_datetime(date_value: Any, time_value: Any) -> datetime | None:
    date_text = _text(date_value)
    time_text = _text(time_value)
    if date_text is None or time_text is None:
        return None
    normalized_time = time_text.zfill(4)
    try:
        return datetime.strptime(
            f"{date_text}{normalized_time}", "%Y%m%d%H%M"
        ).replace(tzinfo=KST)
    except ValueError:
        return None
