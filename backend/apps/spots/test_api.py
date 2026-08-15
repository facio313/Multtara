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

    def test_forecast_summary_reports_stored_source(self):
        response = self.client.get("/api/v1/spots/forecast-summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["days"]), 7)
        self.assertEqual(response.data["source"], "stored")

    def test_detail_includes_safety_tide_and_twin_facts(self):
        response = self.client.get(f"/api/v1/spots/{self.spot.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["safety"]["level"], "safe")
        self.assertIn("next", response.data["tide"])
        self.assertFalse(response.data["livecam"]["is_live"])
        self.assertTrue(response.data["twin_facts"])

    def test_detail_includes_extras_without_seed(self):
        response = self.client.get(f"/api/v1/spots/{self.spot.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["facilities"])
        self.assertEqual(response.data["facilities"][0]["type"], "shower")
        self.assertIsNone(response.data["catch"])
        self.assertIsNone(response.data["hotspring"])
        self.assertIn("asmr_score", response.data["asmr"])
        self.assertIn("predicted_level", response.data["crowd"])
        self.assertIn("best_season", response.data["analytics"])
        self.assertEqual(response.data["quality_trust"]["official_grade"], "1")
        self.assertIsInstance(response.data["golden"], list)

    def test_tidal_and_hotspring_extras(self):
        mud = WaterSpot.objects.create(
            type="tidal_flat",
            name="선재도 갯벌",
            lat=37.25,
            lng=126.53,
            region="인천",
            address="인천",
        )
        onsen = WaterSpot.objects.create(
            type="hotspring",
            name="수안보 온천",
            lat=36.84,
            lng=127.99,
            region="충북",
            address="충북",
        )
        mud_res = self.client.get(f"/api/v1/spots/{mud.id}/")
        self.assertEqual(mud_res.status_code, 200)
        self.assertIsNotNone(mud_res.data["catch"])
        self.assertIn("바지락", mud_res.data["catch"]["species"])
        onsen_res = self.client.get(f"/api/v1/spots/{onsen.id}/")
        self.assertEqual(onsen_res.status_code, 200)
        self.assertEqual(onsen_res.data["hotspring"]["minerals"], "나트륨, 탄산, 황")

    def test_quality_trust_action(self):
        response = self.client.get(f"/api/v1/spots/{self.spot.id}/quality-trust/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["official_grade"], "1")
        self.assertIn("review_signal", response.data)

    def test_safety_radar_lists_sea_and_valley(self):
        WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.8,
            lng=127.5,
            region="경기",
            address="가평",
        )
        response = self.client.get("/api/v1/spots/safety-radar/")
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data]
        self.assertIn("해운대 해수욕장", names)
        self.assertIn("가평 용추계곡", names)
