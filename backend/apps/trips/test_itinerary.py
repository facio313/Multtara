from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary
from apps.users.models import User
from services.water_index import upsert_scores_for_spot

STRONG = "correct-horse-battery-12"


class ItineraryApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(username="planner", password=STRONG)
        self.sea = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산",
        )
        WaterCondition.objects.create(
            spot=self.sea,
            water_temp=25.0,
            air_temp=28.0,
            wind_speed=2.0,
            wave_height=0.4,
            water_quality_grade="1",
            rainfall_recent=0,
        )
        upsert_scores_for_spot(self.sea)
        self.valley = WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.83,
            lng=127.51,
            region="경기",
            address="가평",
        )
        WaterCondition.objects.create(
            spot=self.valley,
            water_temp=18.0,
            air_temp=26.0,
            rainfall_recent=4,
            water_quality_grade="1",
        )
        upsert_scores_for_spot(self.valley)

    def csrf(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.data["csrfToken"]

    def login(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "planner", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_get_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/itinerary/").status_code, 401)

    def test_anonymous_post_does_not_save(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/itinerary/",
            {
                "start_point": "부산",
                "transport": "car",
                "is_day_trip": True,
                "party_size": 2,
                "activity": "swim",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["id"])
        self.assertTrue(response.data["legs"])
        self.assertEqual(response.data["legs"][0]["name"], "해운대 해수욕장")
        self.assertEqual(Itinerary.objects.count(), 0)

    def test_logged_in_post_saves_and_lists(self):
        self.login()
        token = self.csrf()
        created = self.client.post(
            "/api/v1/itinerary/",
            {
                "start_point": "부산",
                "transport": "public",
                "is_day_trip": False,
                "party_size": 4,
                "budget": 80000,
                "activity": "family",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertIsNotNone(created.data["id"])
        self.assertEqual(created.data["transport"], "public")
        self.assertEqual(Itinerary.objects.filter(user=self.user).count(), 1)
        listed = self.client.get("/api/v1/itinerary/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["start_point"], "부산")
        self.assertEqual(listed.data[0]["party_size"], 4)
