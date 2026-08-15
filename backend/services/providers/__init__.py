"""Typed, server-side clients for PongDang's external data providers."""

from .base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderPayloadError,
    ProviderResponseError,
    ProviderResult,
    ProviderTransportError,
)
from .khoa import (
    BeachForecast,
    KhoaClient,
    MudflatForecast,
    RipCurrentForecast,
    SurfForecast,
)

__all__ = [
    "BeachForecast",
    "KhoaClient",
    "MudflatForecast",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderPayloadError",
    "ProviderResponseError",
    "ProviderResult",
    "ProviderTransportError",
    "RipCurrentForecast",
    "SurfForecast",
]
"""External provider clients with sanitized, typed boundaries."""

from .kma import KmaClient, KmaGrid, WeatherValue, latlon_to_grid
from .khoa import KhoaClient
from .tour_api import TourApiClient, TourPlace, TourPlaceDetail

__all__ = [
    "KhoaClient",
    "KmaClient",
    "KmaGrid",
    "TourApiClient",
    "TourPlace",
    "TourPlaceDetail",
    "WeatherValue",
    "latlon_to_grid",
]
