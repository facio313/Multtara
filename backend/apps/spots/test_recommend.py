from django.test import TestCase
from rest_framework.test import APIClient

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from apps.users.models import User
from services.water_index import upsert_scores_for_spot

STRONG = "correct-horse-battery-12"


class RecommendApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.busan = WaterSpot.objects.create(
            type="sea",
            name="송정 해수욕장",
            lat=35.1786,
            lng=129.1996,
            region="부산",
            address="부산 해운대구",
            tags=["#서핑", "#파도"],
        )
        WaterCondition.objects.create(
            spot=self.busan,
            water_temp=23.6,
            air_temp=27.8,
            wind_speed=6.5,
            wave_height=1.4,
            water_quality_grade="1",
            rainfall_recent=2,
            rip_current_risk="medium",
            uv_index=8,
        )
        upsert_scores_for_spot(self.busan)

        self.valley = WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.868,
            lng=127.489,
            region="경기",
            address="가평",
            tags=["#계곡", "#한적한_계곡"],
        )
        WaterCondition.objects.create(
            spot=self.valley,
            water_temp=18.4,
            air_temp=27.0,
            wind_speed=1.2,
            rainfall_recent=8,
            water_level=0.9,
            water_quality_grade="1",
            uv_index=6,
        )
        upsert_scores_for_spot(self.valley)

    def test_anonymous_returns_index_ranking(self):
        response = self.client.get("/api/v1/spots/recommend/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["personalized"])
        self.assertEqual(response.data["activity"], "swim")
        names = [row["name"] for row in response.data["results"]]
        self.assertEqual(set(names), {"송정 해수욕장", "가평 용추계곡"})
        self.assertIn("Water Index", response.data["reason"])

    def test_logged_in_persona_and_region(self):
        user = User.objects.create_user(
            username="waveuser",
            password=STRONG,
            home_region="부산",
            persona_type="surf",
        )
        self.client.force_login(user)
        response = self.client.get("/api/v1/spots/recommend/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["personalized"])
        self.assertEqual(response.data["activity"], "surf")
        self.assertEqual(response.data["results"][0]["name"], "송정 해수욕장")
        self.assertIn("서핑", response.data["reason"])
        self.assertIn("부산", response.data["reason"])
