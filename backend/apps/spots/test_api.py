from django.test import TestCase
from rest_framework.test import APIClient

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from services.water_forecast import upsert_forecast_for_spot
from services.water_index import upsert_scores_for_spot


class SpotApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.spot = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산 해운대구",
            livecam_url="https://picsum.photos/seed/haeundae/800/450",
        )
        WaterCondition.objects.create(
            spot=self.spot,
            water_temp=25.0,
            air_temp=28.0,
            wind_speed=2.0,
            wave_height=0.4,
            water_quality_grade="1",
            rainfall_recent=0,
            rip_current_risk="low",
            uv_index=6,
        )
        upsert_scores_for_spot(self.spot)
        upsert_forecast_for_spot(self.spot)

    def test_ranking_returns_computed_index(self):
        response = self.client.get("/api/v1/spots/ranking/")
        self.assertEqual(response.status_code, 200)
        first = response.data["results"][0]
        self.assertEqual(first["name"], "해운대 해수욕장")
        self.assertEqual(first["type"], "sea")
        self.assertIsNotNone(first["water_index"])
        self.assertGreaterEqual(first["water_index"], 50)

    def test_nested_condition_and_forecast(self):
        condition = self.client.get(f"/api/v1/spots/{self.spot.id}/condition/")
        self.assertEqual(condition.status_code, 200)
        self.assertEqual(condition.data["water_temp"], 25.0)

        forecast = self.client.get(f"/api/v1/spots/{self.spot.id}/forecast/")
        self.assertEqual(forecast.status_code, 200)
        self.assertEqual(len(forecast.data), 7)

    def test_first_swim_respects_threshold(self):
        warm = self.client.get("/api/v1/spots/first-swim/?threshold=22.5")
        self.assertEqual(warm.status_code, 200)
        self.assertEqual(warm.data["count"], 1)

        hot = self.client.get("/api/v1/spots/first-swim/?threshold=30")
        self.assertEqual(hot.status_code, 200)
        self.assertEqual(hot.data["count"], 0)

    def test_livecams_lists_preview_urls(self):
        response = self.client.get("/api/v1/spots/livecams/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
