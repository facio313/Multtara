"""Typed HTTPS boundary for the Valhalla sources-to-targets matrix API."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests

from .base import (
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderTransportError,
)


MAX_MATRIX_LOCATIONS = 50


@dataclass(frozen=True, slots=True)
class RouteLocation:
    spot_id: int
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if self.spot_id < 1:
            raise ValueError("route location spot_id must be positive")
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("route location latitude is invalid")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("route location longitude is invalid")


@dataclass(frozen=True, slots=True)
class RouteMatrixValue:
    origin_spot_id: int
    destination_spot_id: int
    duration_seconds: int
    distance_metres: int | None


@dataclass(frozen=True, slots=True)
class RouteMatrixResult:
    provider: str
    source_url: str
    transport: str
    values: tuple[RouteMatrixValue, ...]


class ValhallaMatrixClient:
    """Fetch a bounded all-to-all route matrix without exposing raw payloads."""

    _COSTING = {
        "drive": "auto",
        "walk": "pedestrian",
        "bicycle": "bicycle",
    }

    def __init__(
        self,
        base_url: str,
        *,
        session: Any | None = None,
        timeout: tuple[float, float] = (3.05, 30.0),
    ) -> None:
        parsed = urlsplit(base_url.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError(
                "Valhalla base URL must be an absolute credential-free HTTPS URL"
            )
        if len(timeout) != 2 or any(value <= 0 for value in timeout):
            raise ProviderConfigurationError(
                "Valhalla connect/read timeouts must both be positive"
            )
        path = parsed.path.rstrip("/")
        self._endpoint = urlunsplit(
            (parsed.scheme, parsed.netloc, f"{path}/sources_to_targets", "", "")
        )
        self._source_url = urlunsplit(
            (parsed.scheme, parsed.netloc, path or "/", "", "")
        )
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"{type(self).__name__}(source_url={self._source_url!r})"

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "ValhallaMatrixClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_matrix(
        self,
        locations: Sequence[RouteLocation],
        *,
        transport: str,
    ) -> RouteMatrixResult:
        normalized = tuple(locations)
        if not 2 <= len(normalized) <= MAX_MATRIX_LOCATIONS:
            raise ValueError(
                f"route matrix requires 2-{MAX_MATRIX_LOCATIONS} locations"
            )
        if len({item.spot_id for item in normalized}) != len(normalized):
            raise ValueError("route matrix spot ids must be unique")
        try:
            costing = self._COSTING[transport]
        except KeyError:
            raise ValueError("unsupported route transport") from None

        coordinates = [
            {"lat": item.latitude, "lon": item.longitude}
            for item in normalized
        ]
        response: Any | None = None
        try:
            response = self._session.post(
                self._endpoint,
                json={
                    "sources": coordinates,
                    "targets": coordinates,
                    "costing": costing,
                    "units": "kilometers",
                },
                timeout=self._timeout,
            )
        except requests.RequestException:
            pass
        if response is None:
            raise ProviderTransportError("VALHALLA")

        failed = False
        try:
            response.raise_for_status()
        except requests.RequestException:
            failed = True
        if failed:
            status_code = getattr(response, "status_code", None)
            raise ProviderTransportError(
                "VALHALLA",
                status_code=status_code if isinstance(status_code, int) else None,
            )

        try:
            payload = response.json()
        except (TypeError, ValueError):
            raise ProviderPayloadError("VALHALLA", "response is not JSON") from None
        if not isinstance(payload, Mapping):
            raise ProviderPayloadError("VALHALLA", "JSON root is not an object")
        matrix = payload.get("sources_to_targets")
        if not isinstance(matrix, list) or len(matrix) != len(normalized):
            raise ProviderPayloadError("VALHALLA", "matrix row count is invalid")

        values: list[RouteMatrixValue] = []
        for origin_index, row in enumerate(matrix):
            if not isinstance(row, list) or len(row) != len(normalized):
                raise ProviderPayloadError(
                    "VALHALLA", "matrix column count is invalid"
                )
            for destination_index, cell in enumerate(row):
                if origin_index == destination_index:
                    continue
                if not isinstance(cell, Mapping):
                    raise ProviderPayloadError("VALHALLA", "matrix cell is invalid")
                duration = _nonnegative_number(cell.get("time"))
                distance_km = _nonnegative_number(cell.get("distance"))
                # Valhalla represents an unreachable pair with null/error-like
                # cell values. Missing pairs stay absent and fail closed later.
                if duration is None:
                    continue
                duration_seconds = max(1, math.ceil(duration))
                distance_metres = (
                    math.ceil(distance_km * 1_000)
                    if distance_km is not None
                    else None
                )
                values.append(
                    RouteMatrixValue(
                        origin_spot_id=normalized[origin_index].spot_id,
                        destination_spot_id=normalized[destination_index].spot_id,
                        duration_seconds=duration_seconds,
                        distance_metres=distance_metres,
                    )
                )

        return RouteMatrixResult(
            provider="valhalla",
            source_url=self._source_url,
            transport=transport,
            values=tuple(values),
        )


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number
