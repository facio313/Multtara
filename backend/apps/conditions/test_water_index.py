from django.test import TestCase

from apps.conditions.models import WaterCondition
from services.water_index import calculate_water_index


def _condition(**kwargs):
    values = {
        "water_temp": 25.0,
        "air_temp": 28.0,
        "wind_speed": 2.0,
        "wave_height": 0.4,
        "water_quality_grade": "1",
        "rainfall_recent": 0.0,
        "rip_current_risk": "low",
        "uv_index": 6.0,
    }
    values.update(kwargs)
    return WaterCondition(**values)


class WaterIndexTests(TestCase):
    def test_calm_warm_sea_is_good_for_swim(self):
        score = calculate_water_index(_condition(), "swim", spot_type="sea")
        self.assertGreaterEqual(score, 70)
        self.assertLessEqual(score, 100)

    def test_high_waves_favor_surf_over_swim(self):
        rough = _condition(wave_height=1.6, wind_speed=8.0)
        swim = calculate_water_index(rough, "swim", spot_type="sea")
        surf = calculate_water_index(rough, "surf", spot_type="sea")
        self.assertGreater(surf, swim)

    def test_colder_air_raises_onsen_score(self):
        cold = calculate_water_index(_condition(air_temp=6.0), "onsen", spot_type="hotspring")
        hot = calculate_water_index(_condition(air_temp=33.0), "onsen", spot_type="hotspring")
        self.assertGreater(cold, hot)

    def test_missing_factors_still_return_bounded_score(self):
        score = calculate_water_index(WaterCondition(), "swim", spot_type="sea")
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
