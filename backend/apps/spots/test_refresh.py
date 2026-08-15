from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot


class RefreshConditionsCommandTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산",
            khoa_obs_code="DT_0005",
            kma_mid_reg_id="11H20000",
        )
        WaterCondition.objects.create(
            spot=self.spot,
            water_temp=24.8,
            air_temp=29.0,
            wind_speed=3.1,
            wave_height=0.7,
            water_quality_grade="1",
            rainfall_recent=0,
        )

    @patch("apps.spots.management.commands.refresh_conditions.sync_tour")
    @patch("apps.spots.management.commands.refresh_conditions.sync_marine")
    @patch("apps.spots.management.commands.refresh_conditions.sync_weather")
    def test_refresh_recomputes_without_network(self, weather, marine, tour):
        weather.return_value = {"changed": ["air_temp"], "saved": True}
        marine.return_value = {"changed": ["water_temp"], "saved": True}
        tour.return_value = {"saved": True, "tourapi_id": "1"}
        out = StringIO()
        call_command("refresh_conditions", spot_id=self.spot.id, stdout=out)
        self.assertIn("Refreshed 1", out.getvalue())
        self.assertEqual(self.spot.forecasts.count(), 7)
        self.assertTrue(self.spot.scores.exists())
