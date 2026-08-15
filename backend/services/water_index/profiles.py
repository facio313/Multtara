"""Versioned, configurable suitability profiles.

Weights are engineering choices, not medical or legal safety limits. The
methodology document records which inputs come from official upstream indices
and which curves require later calibration with Korean field outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .curves import CategoryScores, IDENTITY_SCORE, PiecewiseLinear
from .domain import Activity, MetricValue


ScoreFunction = Callable[[MetricValue], float]


@dataclass(frozen=True, slots=True)
class FactorSpec:
    metric_name: str
    weight: float
    scorer: ScoreFunction
    evidence_basis: str
    max_age_seconds: int | None


@dataclass(frozen=True, slots=True)
class ScoreProfile:
    activity: Activity
    factors: tuple[FactorSpec, ...]
    required_factor_groups: tuple[tuple[str, ...], ...]
    minimum_coverage: float
    limitations: tuple[str, ...]
    minimum_confidence: float = 0.80

    def __post_init__(self) -> None:
        total = sum(factor.weight for factor in self.factors)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{self.activity.value} weights must sum to one, got {total}")
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum coverage must be in (0, 1]")
        if not 0 < self.minimum_confidence <= 1:
            raise ValueError("minimum confidence must be in (0, 1]")


OFFICIAL_GRADE = CategoryScores(
    {
        "very_good": 95,
        "매우좋음": 95,
        "good": 80,
        "좋음": 80,
        "fair": 60,
        "moderate": 60,
        "보통": 60,
        "poor": 35,
        "나쁨": 35,
        "very_poor": 15,
        "매우나쁨": 15,
    }
)

CROWD = CategoryScores(
    {
        "low": 100,
        "낮음": 100,
        "medium": 65,
        "보통": 65,
        "high": 30,
        "높음": 30,
        "very_high": 10,
        "매우높음": 10,
    }
)

SWIM_WATER_TEMPERATURE = PiecewiseLinear(
    ((5, 0), (14.99, 0), (15, 10), (16, 30), (18, 55), (20, 75), (23, 90), (26, 100), (30, 100), (31, 50), (31.01, 0), (36, 0))
)
OUTDOOR_AIR_COMFORT = PiecewiseLinear(
    ((-10, 0), (5, 10), (15, 45), (22, 90), (26, 100), (31, 80), (35, 40), (40, 0))
)
COOL_WEATHER_ONSEN = PiecewiseLinear(
    ((-15, 100), (0, 100), (10, 90), (20, 65), (28, 35), (35, 10), (40, 0))
)
CALM_WIND = PiecewiseLinear(((0, 100), (3, 100), (6, 80), (8.3, 55), (10.8, 25), (14, 0)))
LIGHT_WAVES = PiecewiseLinear(((0, 100), (0.3, 95), (0.6, 75), (0.9, 40), (1.2, 10), (1.5, 0)))
LOW_RAIN = PiecewiseLinear(((0, 100), (0.1, 80), (1, 60), (3, 35), (15, 0)))
UV_COMFORT = PiecewiseLinear(((0, 100), (2, 100), (5, 80), (7, 60), (10, 35), (11, 25), (15, 0)))
USER_RATING = PiecewiseLinear(((1, 0), (2, 25), (3, 50), (4, 80), (5, 100)))
PROPORTION_SCORE = PiecewiseLinear(((0, 0), (1, 100)))


PROFILES: dict[Activity, ScoreProfile] = {
    Activity.SWIM: ScoreProfile(
        activity=Activity.SWIM,
        factors=(
            FactorSpec("official_activity_grade", 0.45, OFFICIAL_GRADE, "official_khoa_index", 43_200),
            FactorSpec("water_temperature_c", 0.15, SWIM_WATER_TEMPERATURE, "research_informed_engineering_curve", 10_800),
            FactorSpec("air_temperature_c", 0.10, OUTDOOR_AIR_COMFORT, "recreation_weather_research", 10_800),
            FactorSpec("wave_height_m", 0.10, LIGHT_WAVES, "family_swim_engineering_curve", 3_600),
            FactorSpec("wind_speed_ms", 0.08, CALM_WIND, "recreation_weather_research", 3_600),
            FactorSpec("precipitation_1h_mm", 0.05, LOW_RAIN, "recreation_weather_research", 3_600),
            FactorSpec("uv_index", 0.03, UV_COMFORT, "who_uv_guidance", 10_800),
            FactorSpec("crowd_level", 0.04, CROWD, "product_preference", 3_600),
        ),
        required_factor_groups=(("official_activity_grade",),),
        minimum_coverage=0.80,
        limitations=(
            "Suitability curves are not a declaration that swimming is safe.",
            "Official KHOA grades are converted to display anchors, not represented as official numeric scores.",
        ),
    ),
    Activity.SURF: ScoreProfile(
        activity=Activity.SURF,
        factors=(
            FactorSpec("official_activity_grade", 0.80, OFFICIAL_GRADE, "official_khoa_skill_specific_index", 43_200),
            FactorSpec("crowd_level", 0.10, CROWD, "product_preference", 3_600),
            FactorSpec("uv_index", 0.10, UV_COMFORT, "who_uv_guidance", 10_800),
        ),
        required_factor_groups=(("official_activity_grade",),),
        minimum_coverage=0.80,
        limitations=(
            "The KHOA grade must match the surfer skill level; PongDang does not infer skill.",
            "Generic wave-height thresholds are not used as a universal surf safety rule.",
        ),
    ),
    Activity.RELAX: ScoreProfile(
        activity=Activity.RELAX,
        factors=(
            FactorSpec("hci_beach_score", 0.90, IDENTITY_SCORE, "hci_beach_rutty_2020", 10_800),
            FactorSpec("crowd_level", 0.10, CROWD, "product_preference", 3_600),
        ),
        required_factor_groups=(("hci_beach_score",),),
        minimum_coverage=0.90,
        limitations=(
            "HCI:Beach estimates outdoor climate comfort, not water-contact safety or a mental-health outcome.",
            "Hourly hazards must not be hidden by daily HCI component averages.",
        ),
    ),
    Activity.MUDFLAT: ScoreProfile(
        activity=Activity.MUDFLAT,
        factors=(
            FactorSpec("official_activity_grade", 0.85, OFFICIAL_GRADE, "official_khoa_tide_weather_index", 43_200),
            FactorSpec("crowd_level", 0.10, CROWD, "product_preference", 3_600),
            FactorSpec("uv_index", 0.05, UV_COMFORT, "who_uv_guidance", 10_800),
        ),
        required_factor_groups=(("official_activity_grade",),),
        minimum_coverage=0.85,
        limitations=("Only the official experience window may define tide eligibility.",),
    ),
    Activity.ONSEN: ScoreProfile(
        activity=Activity.ONSEN,
        factors=(
            FactorSpec("facility_operation_confidence", 0.40, PROPORTION_SCORE, "verified_facility_data", 1_800),
            FactorSpec("crowd_fit", 0.20, PROPORTION_SCORE, "product_preference", 3_600),
            FactorSpec("amenity_fit", 0.20, PROPORTION_SCORE, "explicit_user_requirements", 86_400),
            FactorSpec("indoor_weather_shelter", 0.10, PROPORTION_SCORE, "product_policy", 86_400),
            FactorSpec("preferred_temperature_fit", 0.10, PROPORTION_SCORE, "explicit_user_preference", 1_800),
        ),
        required_factor_groups=(("facility_operation_confidence",), ("amenity_fit",)),
        minimum_coverage=0.70,
        limitations=(
            "This is a facility suitability score, not a medical efficacy or bathing-risk assessment.",
            "No health benefit is inferred from mineral composition.",
        ),
    ),
    Activity.RAFTING: ScoreProfile(
        activity=Activity.RAFTING,
        factors=(
            FactorSpec("flow_suitability_score", 0.60, IDENTITY_SCORE, "site_specific_hydraulic_thresholds", 900),
            FactorSpec("operator_readiness", 0.20, PROPORTION_SCORE, "licensed_operator_status", 900),
            FactorSpec("flow_trend_stability", 0.10, PROPORTION_SCORE, "site_specific_hydrology", 900),
            FactorSpec("thermal_gear_readiness", 0.10, PROPORTION_SCORE, "equipment_readiness", 900),
        ),
        required_factor_groups=(
            ("flow_suitability_score",),
            ("operator_readiness",),
            ("thermal_gear_readiness",),
        ),
        minimum_coverage=0.90,
        limitations=(
            "River level and flow thresholds must be site-specific; no universal threshold is inferred.",
            "A licensed operator or local authority remains the decision-maker.",
        ),
    ),
}
