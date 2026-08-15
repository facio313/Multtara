from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.conditions.models import WaterCondition
from apps.spots.models import NearbyFacility, WaterSpot
from apps.trips.models import SafetyCard
from apps.users.models import User

STRONG = "correct-horse-battery-12"


class SafetyCardApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(username="safewalker", password=STRONG)
        self.spot = WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.83,
            lng=127.51,
            region="경기",
            address="가평군 가평읍",
        )
        WaterCondition.objects.create(
            spot=self.spot,
            rainfall_recent=12,
            water_level=0.9,
            weather_alert="호우주의보",
        )
        NearbyFacility.objects.create(
            spot=self.spot,
            type="hospital",
            name="가평의료원",
            lat=37.831,
            lng=127.511,
            tag="병원",
            distance_min=8,
        )

    def csrf(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.data["csrfToken"]

    def login(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "safewalker", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/safety-card/").status_code, 401)
        token = self.csrf()
        denied = self.client.post(
            "/api/v1/safety-card/",
            {"spot_id": self.spot.id},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(denied.status_code, 401)

    def test_creates_snapshot_and_lists_cards(self):
        self.login()
        token = self.csrf()
        created = self.client.post(
            "/api/v1/safety-card/",
            {"spot_id": self.spot.id, "shared_with": ["가족"]},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["spot"]["name"], "가평 용추계곡")
        self.assertEqual(created.data["emergency"], "119")
        self.assertEqual(created.data["shared_with"], ["가족"])
        self.assertIn("가평의료원", created.data["nearest_safety_facility"])
        self.assertEqual(created.data["safety"]["level"], "danger")
        self.assertTrue(created.data["risk_factors"])

        listed = self.client.get("/api/v1/safety-card/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        detail = self.client.get(f"/api/v1/safety-card/{created.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["id"], created.data["id"])
        self.assertEqual(SafetyCard.objects.filter(user=self.user).count(), 1)

    def test_other_user_cannot_read_card(self):
        self.login()
        token = self.csrf()
        created = self.client.post(
            "/api/v1/safety-card/",
            {"spot_id": self.spot.id},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        other = User.objects.create_user(username="otherwalk", password=STRONG)
        self.client.force_login(other)
        hidden = self.client.get(f"/api/v1/safety-card/{created.data['id']}/")
        self.assertEqual(hidden.status_code, 404)
