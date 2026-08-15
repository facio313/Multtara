"""Typed client for the Korea Tourism Organization TourAPI v2 gateways."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping
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
class TourPlace:
    content_id: str
    content_type_id: str | None
    title: str | None
    address: str | None
    detail_address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    distance_m: Decimal | None
    image_url: str | None
    thumbnail_url: str | None
    area_code: str | None
    district_code: str | None
    category_large: str | None
    category_medium: str | None
    category_small: str | None
    telephone: str | None
    modified_at: datetime | None


@dataclass(frozen=True, slots=True)
class TourPlaceDetail:
    content_id: str
    content_type_id: str | None
    title: str | None
    address: str | None
    detail_address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    image_url: str | None
    thumbnail_url: str | None
    telephone: str | None
    homepage: str | None
    overview: str | None
    modified_at: datetime | None


class TourApiClient(JsonProviderClient):
    """Language-aware server-side TourAPI client.

    TourAPI HTML fields are retained as provider text. Consumers must sanitize
    them before rendering and must not treat provider image URLs as owned assets.
    """

    BASE_URL = "https://apis.data.go.kr"
    SOURCE_URL = "https://www.data.go.kr/data/15101578/openapi.do"
    SERVICE_BY_LANGUAGE = {
        "ko": "KorService2",
        "en": "EngService2",
        "ja": "JpnService2",
        "zh-hans": "ChsService2",
        "zh-hant": "ChtService2",
    }

    def __init__(
        self,
        service_key: str,
        *,
        language: str = "ko",
        mobile_app: str = "PongDang",
        session: Any | None = None,
        timeout: tuple[float, float] = (3.05, 10.0),
        max_retries: int = 2,
        backoff_factor: float = 0.25,
        page_size: int = 100,
        max_pages: int = 20,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(service_key, str) or not service_key.strip():
            raise ProviderConfigurationError("TourAPI service key is required")
        normalized_language = language.strip().lower()
        if normalized_language not in self.SERVICE_BY_LANGUAGE:
            raise ProviderConfigurationError("unsupported TourAPI language")
        normalized_app = mobile_app.strip()
        if not normalized_app or len(normalized_app) > 50:
            raise ProviderConfigurationError("TourAPI mobile_app is invalid")
        if not 1 <= page_size <= 1000:
            raise ProviderConfigurationError("TourAPI page_size must be between 1 and 1000")
        if not 1 <= max_pages <= 100:
            raise ProviderConfigurationError("TourAPI max_pages must be between 1 and 100")
        kwargs: dict[str, Any] = {
            "provider": "TourAPI",
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
        self._service = self.SERVICE_BY_LANGUAGE[normalized_language]
        self._language = normalized_language
        self._mobile_app = normalized_app
        self._page_size = page_size
        self._max_pages = max_pages

    @property
    def language(self) -> str:
        return self._language

    def fetch_nearby(
        self,
        *,
        latitude: float | Decimal,
        longitude: float | Decimal,
        radius_m: int = 20_000,
        content_type_id: str | None = None,
        image_required: bool = False,
    ) -> ProviderResult[TourPlace]:
        lat = _coordinate(latitude, "latitude", -90, 90)
        lon = _coordinate(longitude, "longitude", -180, 180)
        if isinstance(radius_m, bool) or not isinstance(radius_m, int) or not 1 <= radius_m <= 20_000:
            raise ValueError("radius_m must be an integer between 1 and 20000")
        return self._fetch_all(
            "locationBasedList2",
            self._parse_place,
            {
                "mapX": str(lon),
                "mapY": str(lat),
                "radius": radius_m,
                "arrange": "S" if image_required else "E",
                **({"contentTypeId": content_type_id.strip()} if content_type_id and content_type_id.strip() else {}),
            },
        )

    def search_keyword(
        self,
        keyword: str,
        *,
        area_code: str | None = None,
        district_code: str | None = None,
        content_type_id: str | None = None,
        image_required: bool = False,
    ) -> ProviderResult[TourPlace]:
        normalized_keyword = keyword.strip()
        if not normalized_keyword or len(normalized_keyword) > 100:
            raise ValueError("keyword must contain between 1 and 100 characters")
        optional = {
            "areaCode": area_code,
            "sigunguCode": district_code,
            "contentTypeId": content_type_id,
        }
        return self._fetch_all(
            "searchKeyword2",
            self._parse_place,
            {
                "keyword": normalized_keyword,
                "arrange": "O" if image_required else "A",
                **{
                    key: value.strip()
                    for key, value in optional.items()
                    if isinstance(value, str) and value.strip()
                },
            },
        )

    def fetch_detail(self, content_id: str) -> ProviderResult[TourPlaceDetail]:
        normalized_id = content_id.strip()
        if not normalized_id or len(normalized_id) > 100:
            raise ValueError("content_id is invalid")
        return self._fetch_all(
            "detailCommon2",
            self._parse_detail,
            {
                "contentId": normalized_id,
                "defaultYN": "Y",
                "firstImageYN": "Y",
                "areacodeYN": "Y",
                "catcodeYN": "Y",
                "addrinfoYN": "Y",
                "mapinfoYN": "Y",
                "overviewYN": "Y",
            },
        )

    def _fetch_all(
        self,
        operation: str,
        parser: Callable[[Mapping[str, Any]], Any],
        request_params: Mapping[str, Any],
    ) -> ProviderResult[Any]:
        endpoint = f"/B551011/{self._service}/{operation}"
        common: dict[str, Any] = {
            "serviceKey": self.__service_key,
            "MobileOS": "WEB",
            "MobileApp": self._mobile_app,
            "_type": "json",
            "numOfRows": self._page_size,
            **request_params,
        }
        records: list[Any] = []
        total: int | None = None
        for page in range(1, self._max_pages + 1):
            payload = self._get_json(endpoint, {**common, "pageNo": page})
            body = self._validated_body(payload)
            items = _normalize_items(body.get("items"))
            if total is None:
                total = _integer(body.get("totalCount"))
                if total is not None:
                    total = max(total, 0)
            records.extend(parser(item) for item in items)
            if total is not None and len(records) >= total:
                break
            if not items:
                if total is not None and len(records) < total:
                    raise ProviderPayloadError(
                        "TourAPI", "pagination ended before the advertised total"
                    )
                break
            if total is None and len(items) < self._page_size:
                break
        else:
            raise ProviderPayloadError("TourAPI", "pagination exceeded its safety limit")
        return ProviderResult(
            provider="TourAPI",
            endpoint=endpoint,
            records=tuple(records),
            reported_total_count=total,
        )

    @staticmethod
    def _validated_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = payload.get("response", payload)
        if not isinstance(envelope, Mapping):
            raise ProviderPayloadError("TourAPI", "response envelope is not an object")
        header = envelope.get("header")
        if not isinstance(header, Mapping):
            raise ProviderPayloadError("TourAPI", "response header is missing")
        result_code = _text(header.get("resultCode"))
        if result_code is None:
            raise ProviderPayloadError("TourAPI", "resultCode is missing")
        if result_code not in {"0000", "00"}:
            raise ProviderResponseError("TourAPI", result_code)
        body = envelope.get("body")
        if not isinstance(body, Mapping):
            raise ProviderPayloadError("TourAPI", "response body is missing")
        return body

    @staticmethod
    def _parse_place(item: Mapping[str, Any]) -> TourPlace:
        content_id = _text(item.get("contentid"))
        if content_id is None:
            raise ProviderPayloadError("TourAPI", "contentid is missing")
        return TourPlace(
            content_id=content_id,
            content_type_id=_text(item.get("contenttypeid")),
            title=_text(item.get("title")),
            address=_text(item.get("addr1")),
            detail_address=_text(item.get("addr2")),
            latitude=_decimal(item.get("mapy")),
            longitude=_decimal(item.get("mapx")),
            distance_m=_decimal(item.get("dist")),
            image_url=_https_url(item.get("firstimage")),
            thumbnail_url=_https_url(item.get("firstimage2")),
            area_code=_text(item.get("areacode")),
            district_code=_text(item.get("sigungucode")),
            category_large=_text(item.get("cat1", item.get("lclsSystm1"))),
            category_medium=_text(item.get("cat2", item.get("lclsSystm2"))),
            category_small=_text(item.get("cat3", item.get("lclsSystm3"))),
            telephone=_text(item.get("tel")),
            modified_at=_provider_datetime(item.get("modifiedtime")),
        )

    @staticmethod
    def _parse_detail(item: Mapping[str, Any]) -> TourPlaceDetail:
        content_id = _text(item.get("contentid"))
        if content_id is None:
            raise ProviderPayloadError("TourAPI", "contentid is missing")
        return TourPlaceDetail(
            content_id=content_id,
            content_type_id=_text(item.get("contenttypeid")),
            title=_text(item.get("title")),
            address=_text(item.get("addr1")),
            detail_address=_text(item.get("addr2")),
            latitude=_decimal(item.get("mapy")),
            longitude=_decimal(item.get("mapx")),
            image_url=_https_url(item.get("firstimage")),
            thumbnail_url=_https_url(item.get("firstimage2")),
            telephone=_text(item.get("tel")),
            homepage=_text(item.get("homepage")),
            overview=_text(item.get("overview")),
            modified_at=_provider_datetime(item.get("modifiedtime")),
        )


def _coordinate(value: float | Decimal, name: str, lower: int, upper: int) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} is invalid") from None
    if not parsed.is_finite() or not lower <= parsed <= upper:
        raise ValueError(f"{name} is outside geographic bounds")
    return parsed


def _normalize_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, Mapping):
        value = value.get("item")
    if value is None or value == "":
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(value)
    raise ProviderPayloadError("TourAPI", "items.item is neither an object nor a list")


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


def _provider_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def _https_url(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if text.startswith("https://"):
        return text
    if text.startswith("http://"):
        return f"https://{text.removeprefix('http://')}"
    return None
