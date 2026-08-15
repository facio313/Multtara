"""Typed client for the KHOA public-data gateway APIs.

The endpoint and field names follow the 2026 Public Data Portal contracts for the
National Oceanographic Research Institute (provider code 1192136). KHOA's
``totalIndex`` is an official Korean five-level grade in current responses. It is
therefore retained as text and is never converted into an invented numeric score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, TypeVar

from .base import (
    JsonProviderClient,
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderResponseError,
    ProviderResult,
)


ParsedRecordT = TypeVar("ParsedRecordT")


@dataclass(frozen=True, slots=True)
class BeachForecast:
    place_name: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    forecast_date: date | None
    forecast_time_code: str | None
    score: Decimal | None
    official_grade: str | None
    maximum_wave_height: Decimal | None
    average_water_temperature: Decimal | None
    average_air_temperature: Decimal | None
    maximum_wind_speed: Decimal | None


@dataclass(frozen=True, slots=True)
class SurfForecast:
    place_name: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    forecast_date: date | None
    forecast_time_code: str | None
    score: Decimal | None
    official_grade: str | None
    grade_detail: str | None
    average_wave_height: Decimal | None
    average_wave_period: Decimal | None
    average_wind_speed: Decimal | None
    average_water_temperature: Decimal | None


@dataclass(frozen=True, slots=True)
class MudflatForecast:
    place_name: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    forecast_date: date | None
    experience_start_time: str | None
    experience_end_time: str | None
    weather: str | None
    score: Decimal | None
    official_grade: str | None
    maximum_air_temperature: Decimal | None
    minimum_air_temperature: Decimal | None
    maximum_wind_speed: Decimal | None
    minimum_wind_speed: Decimal | None


@dataclass(frozen=True, slots=True)
class RipCurrentForecast:
    beach_code: str | None
    beach_name: str | None
    observed_at: datetime | None
    latitude: Decimal | None
    longitude: Decimal | None
    official_index: str | None
    index_value: Decimal | None
    risk_message: str | None
    wave_height_m: Decimal | None
    wave_period_seconds: Decimal | None
    water_temperature_celsius: Decimal | None
    air_temperature_celsius: Decimal | None
    wind_direction: str | None
    wind_speed_mps: Decimal | None


class KhoaClient(JsonProviderClient):
    """Server-side client for KHOA marine activity and rip-current data."""

    BASE_URL = "https://apis.data.go.kr"
    BEACH_ENDPOINT = "/1192136/fcstBeachv2/GetFcstBeachApiServicev2"
    SURF_ENDPOINT = "/1192136/fcstSurfingv2/GetFcstSurfingApiServicev2"
    MUDFLAT_ENDPOINT = "/1192136/fcstMudflatv2/GetFcstMudflatApiServicev2"
    RIP_CURRENT_ENDPOINT = "/1192136/ripCurrent/GetRipCurrentApiService"

    def __init__(
        self,
        service_key: str,
        *,
        session: Any | None = None,
        timeout: tuple[float, float] = (3.05, 10.0),
        max_retries: int = 2,
        backoff_factor: float = 0.25,
        page_size: int = 300,
        max_pages: int = 1000,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(service_key, str) or not service_key.strip():
            raise ProviderConfigurationError("KHOA service key is required")
        if not 1 <= page_size <= 300:
            raise ProviderConfigurationError("KHOA page_size must be between 1 and 300")
        if not 1 <= max_pages <= 1000:
            raise ProviderConfigurationError("KHOA max_pages must be between 1 and 1000")

        base_kwargs: dict[str, Any] = {
            "provider": "KHOA",
            "base_url": self.BASE_URL,
            "session": session,
            "timeout": timeout,
            "max_retries": max_retries,
            "backoff_factor": backoff_factor,
        }
        if sleeper is not None:
            base_kwargs["sleeper"] = sleeper
        super().__init__(**base_kwargs)
        self.__service_key = service_key.strip()
        self._page_size = page_size
        self._max_pages = max_pages

    def fetch_beach_forecasts(
        self,
        *,
        request_date: date | str | None = None,
        place_code: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
    ) -> ProviderResult[BeachForecast]:
        return self._fetch_all(
            self.BEACH_ENDPOINT,
            self._parse_beach,
            request_date=request_date,
            place_code=place_code,
            include=include,
            exclude=exclude,
        )

    def fetch_surf_forecasts(
        self,
        *,
        request_date: date | str | None = None,
        place_code: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
    ) -> ProviderResult[SurfForecast]:
        return self._fetch_all(
            self.SURF_ENDPOINT,
            self._parse_surf,
            request_date=request_date,
            place_code=place_code,
            include=include,
            exclude=exclude,
        )

    def fetch_mudflat_forecasts(
        self,
        *,
        request_date: date | str | None = None,
        place_code: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
    ) -> ProviderResult[MudflatForecast]:
        return self._fetch_all(
            self.MUDFLAT_ENDPOINT,
            self._parse_mudflat,
            request_date=request_date,
            place_code=place_code,
            include=include,
            exclude=exclude,
        )

    def fetch_rip_current_forecasts(
        self,
        *,
        beach_code: str,
        request_date: date | str | None = None,
        include: str | None = None,
        exclude: str | None = None,
    ) -> ProviderResult[RipCurrentForecast]:
        normalized_beach_code = _text(beach_code)
        if normalized_beach_code is None:
            raise ValueError("beach_code is required")
        return self._fetch_all(
            self.RIP_CURRENT_ENDPOINT,
            self._parse_rip_current,
            request_date=request_date,
            beach_code=normalized_beach_code,
            include=include,
            exclude=exclude,
        )

    def _fetch_all(
        self,
        endpoint: str,
        parser: Callable[[Mapping[str, Any]], ParsedRecordT],
        *,
        request_date: date | str | None,
        place_code: str | None = None,
        beach_code: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
    ) -> ProviderResult[ParsedRecordT]:
        params: dict[str, Any] = {
            "serviceKey": self.__service_key,
            "type": "json",
            "numOfRows": self._page_size,
        }
        optional_params = {
            "reqDate": _format_request_date(request_date),
            "placeCode": _text(place_code),
            "beachCode": _text(beach_code),
            "include": _text(include),
            "exclude": _text(exclude),
        }
        params.update({key: value for key, value in optional_params.items() if value})

        records: list[ParsedRecordT] = []
        reported_total: int | None = None

        for requested_page in range(1, self._max_pages + 1):
            params["pageNo"] = requested_page
            payload = self._get_json(endpoint, params)
            body = self._validated_body(payload)
            raw_items = _normalize_items(body.get("items"))

            if reported_total is None:
                candidate_total = _integer(body.get("totalCount"))
                if candidate_total is not None:
                    reported_total = max(candidate_total, 0)

            records.extend(parser(item) for item in raw_items)

            if reported_total is not None and len(records) >= reported_total:
                break
            if not raw_items:
                if reported_total is not None and len(records) < reported_total:
                    raise ProviderPayloadError(
                        "KHOA", "pagination ended before the advertised total"
                    )
                break

            response_page_size = _integer(body.get("numOfRows"))
            effective_page_size = (
                response_page_size
                if response_page_size is not None and response_page_size > 0
                else self._page_size
            )
            if reported_total is None and len(raw_items) < effective_page_size:
                break
        else:
            raise ProviderPayloadError("KHOA", "pagination exceeded its safety limit")

        return ProviderResult(
            provider="KHOA",
            endpoint=endpoint,
            records=tuple(records),
            reported_total_count=reported_total,
        )

    @staticmethod
    def _validated_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = payload.get("response", payload)
        if not isinstance(envelope, Mapping):
            raise ProviderPayloadError("KHOA", "response envelope is not an object")

        header = envelope.get("header")
        if not isinstance(header, Mapping):
            raise ProviderPayloadError("KHOA", "response header is missing")
        result_code = _text(header.get("resultCode"))
        if result_code is None:
            raise ProviderPayloadError("KHOA", "resultCode is missing")
        if result_code != "00":
            # Do not expose resultMsg: provider messages are outside our trust boundary.
            raise ProviderResponseError("KHOA", result_code)

        body = envelope.get("body")
        if not isinstance(body, Mapping):
            raise ProviderPayloadError("KHOA", "response body is missing")
        return body

    @staticmethod
    def _parse_beach(item: Mapping[str, Any]) -> BeachForecast:
        return BeachForecast(
            place_name=_text(item.get("bbchNm")),
            latitude=_decimal(item.get("lat")),
            longitude=_decimal(item.get("lot")),
            forecast_date=_date(item.get("predcYmd")),
            forecast_time_code=_text(item.get("predcNoonSeCd")),
            score=_decimal(item.get("lastScr")),
            official_grade=_text(item.get("totalIndex")),
            maximum_wave_height=_decimal(item.get("maxWvhgt")),
            average_water_temperature=_decimal(item.get("avgWtem")),
            average_air_temperature=_decimal(item.get("avgArtmp")),
            maximum_wind_speed=_decimal(item.get("maxWspd")),
        )

    @staticmethod
    def _parse_surf(item: Mapping[str, Any]) -> SurfForecast:
        return SurfForecast(
            place_name=_text(item.get("surfPlcNm")),
            latitude=_decimal(item.get("lat")),
            longitude=_decimal(item.get("lot")),
            forecast_date=_date(item.get("predcYmd")),
            forecast_time_code=_text(item.get("predcNoonSeCd")),
            score=_decimal(item.get("lastScr")),
            official_grade=_text(item.get("totalIndex")),
            grade_detail=_text(item.get("grdCn", item.get("GrdCn"))),
            average_wave_height=_decimal(item.get("avgWvhgt")),
            average_wave_period=_decimal(item.get("avgWvpd")),
            average_wind_speed=_decimal(item.get("avgWspd")),
            average_water_temperature=_decimal(item.get("avgWtem")),
        )

    @staticmethod
    def _parse_mudflat(item: Mapping[str, Any]) -> MudflatForecast:
        return MudflatForecast(
            place_name=_text(item.get("mdftExpcnVlgNm")),
            latitude=_decimal(item.get("lat")),
            longitude=_decimal(item.get("lot")),
            forecast_date=_date(item.get("predcYmd")),
            experience_start_time=_text(item.get("mdftExprnBgngTm")),
            experience_end_time=_text(item.get("mdftExprnEndTm")),
            weather=_text(item.get("weather")),
            score=_decimal(item.get("lastScr")),
            official_grade=_text(item.get("totalIndex")),
            maximum_air_temperature=_decimal(item.get("maxArtmp")),
            minimum_air_temperature=_decimal(item.get("minArtmp")),
            maximum_wind_speed=_decimal(item.get("maxWspd")),
            minimum_wind_speed=_decimal(item.get("minWspd")),
        )

    @staticmethod
    def _parse_rip_current(item: Mapping[str, Any]) -> RipCurrentForecast:
        official_index = _text(item.get("lastScr"))
        return RipCurrentForecast(
            beach_code=_text(item.get("obsvtrId")),
            beach_name=_text(item.get("obsvtrNm")),
            observed_at=_datetime(item.get("obsrvnDt")),
            latitude=_decimal(item.get("lat")),
            longitude=_decimal(item.get("lot")),
            official_index=official_index,
            index_value=_decimal(official_index),
            risk_message=_text(item.get("lastScrCn")),
            wave_height_m=_decimal(item.get("wvhgt")),
            wave_period_seconds=_decimal(item.get("wvpd")),
            water_temperature_celsius=_decimal(item.get("wtem")),
            air_temperature_celsius=_decimal(item.get("artmp")),
            wind_direction=_text(item.get("wndrct")),
            wind_speed_mps=_decimal(item.get("wspd")),
        )


def _normalize_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ()

    if isinstance(value, Mapping):
        if "item" not in value:
            if not value:
                return ()
            raise ProviderPayloadError("KHOA", "items.item is missing")
        value = value.get("item")

    if value is None or (isinstance(value, str) and not value.strip()):
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (list, tuple)):
        if not all(isinstance(item, Mapping) for item in value):
            raise ProviderPayloadError("KHOA", "items contain a non-object value")
        return tuple(value)
    raise ProviderPayloadError("KHOA", "items.item is neither an object nor a list")


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


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


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if text is None:
        return None
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = _text(value)
    if text is None:
        return None

    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    for format_string in (
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d%H",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, format_string)
        except ValueError:
            continue
    return None


def _format_request_date(value: date | str | None) -> str | None:
    if value is None:
        return None
    parsed = _date(value)
    if parsed is None:
        raise ValueError("request_date must be YYYYMMDD, YYYY-MM-DD, or a date")
    return parsed.strftime("%Y%m%d")
