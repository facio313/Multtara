"""Holiday Climate Index for beaches (HCI:Beach).

The component tables and 2:4:3:1 weighting follow Rutty et al. (2020). The
result is a climate-comfort score, not a mental-health or coastal-safety score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .curves import clamp_score


@dataclass(frozen=True, slots=True)
class HCIBeachResult:
    score: int
    thermal_comfort: int
    aesthetic: int
    precipitation: int
    wind: int


def humidex_from_dew_point(air_temperature_c: float, dew_point_c: float) -> float:
    """Calculate Canadian Humidex from air temperature and dew point."""

    vapour_pressure = 6.11 * math.exp(
        5417.7530 * ((1 / 273.16) - (1 / (273.15 + float(dew_point_c))))
    )
    return float(air_temperature_c) + (5 / 9) * (vapour_pressure - 10)


def _thermal_score(humidex: float) -> int:
    if humidex < 10:
        return -10
    bands = (
        (15, -5), (17, 0), (18, 1), (19, 2), (20, 3), (21, 4),
        (22, 5), (23, 6), (26, 7), (28, 9), (31, 10), (33, 9),
        (34, 8), (35, 7), (36, 6), (37, 5), (38, 4), (39, 2),
    )
    for upper, score in bands:
        if humidex < upper:
            return score
    return 0


def _aesthetic_score(cloud_cover_pct: float) -> int:
    cloud = max(0.0, min(100.0, float(cloud_cover_pct)))
    bands = (
        (1, 8), (15, 9), (26, 10), (36, 9), (46, 8),
        (56, 7), (66, 6), (76, 5), (86, 4), (96, 3), (101, 2),
    )
    return next(score for upper, score in bands if cloud < upper)


def _precipitation_score(daily_precipitation_mm: float) -> int:
    rain = max(0.0, float(daily_precipitation_mm))
    if rain == 0:
        return 10
    bands = ((3, 9), (6, 8), (9, 6), (12, 4), (25, 0))
    for upper, score in bands:
        if rain < upper:
            return score
    return -1


def _wind_score(average_wind_kmh: float) -> int:
    wind = max(0.0, float(average_wind_kmh))
    bands = (
        (0.6, 8), (10, 10), (20, 9), (30, 8),
        (40, 6), (50, 3), (70, 0),
    )
    for upper, score in bands:
        if wind < upper:
            return score
    return -10


def calculate_hci_beach(
    *,
    humidex: float,
    cloud_cover_pct: float,
    daily_precipitation_mm: float,
    average_wind_kmh: float,
) -> HCIBeachResult:
    """Return the exact HCI:Beach component sum, clipped for product display."""

    thermal = _thermal_score(float(humidex))
    aesthetic = _aesthetic_score(float(cloud_cover_pct))
    precipitation = _precipitation_score(float(daily_precipitation_mm))
    wind = _wind_score(float(average_wind_kmh))
    raw = 2 * thermal + 4 * aesthetic + 3 * precipitation + wind
    return HCIBeachResult(
        score=round(clamp_score(raw)),
        thermal_comfort=thermal,
        aesthetic=aesthetic,
        precipitation=precipitation,
        wind=wind,
    )
