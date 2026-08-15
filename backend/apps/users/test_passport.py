from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.spots.models import WaterSpot
from apps.users.models import Passport, User

STRONG = "correct-horse-battery-12"


class PassportApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(username="stamper", password=STRONG)
        self.sea = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산",
        )
        self.valley = WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.83,
            lng=127.51,
            region="경기",
            address="가평",
        )

    def csrf(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.data["csrfToken"]

    def login(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "stamper", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/passport/").status_code, 401)
        token = self.csrf()
        denied = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 35.16, "lng": 129.16},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(denied.status_code, 401)

    def test_checkin_requires_location(self):
        self.login()
        token = self.csrf()
        missing = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(Passport.objects.count(), 0)

    def test_checkin_awards_badges_and_blocks_duplicate(self):
        self.login()
        token = self.csrf()
        created = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 35.16, "lng": 129.16},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["visited_count"], 1)
        ids = [badge["id"] for badge in created.data["badges"]]
        self.assertIn("first_dip", ids)
        self.assertIn("sea_1", ids)

        token = self.csrf()
        duplicate = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 35.16, "lng": 129.16},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(Passport.objects.filter(user=self.user).count(), 1)

        token = self.csrf()
        valley = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.valley.id, "lat": 37.83, "lng": 127.51},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(valley.status_code, 201)
        ids = [badge["id"] for badge in valley.data["badges"]]
        self.assertIn("valley_1", ids)
        collection = {row["type"]: row for row in valley.data["collection"]}
        self.assertEqual(collection["sea"]["visited"], 1)
        self.assertEqual(collection["valley"]["visited"], 1)

        summary = self.client.get("/api/v1/passport/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["visited_count"], 2)
        self.assertEqual(len(self.client.get("/api/v1/passport/badges/").data), len(summary.data["badges"]))

    def test_far_away_checkin_is_rejected(self):
        self.login()
        token = self.csrf()
        response = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 37.5665, "lng": 126.9780},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Passport.objects.count(), 0)

    def test_nearby_checkin_is_allowed(self):
        self.login()
        token = self.csrf()
        response = self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 35.16, "lng": 129.16},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201)

    def test_checkin_accepts_eco_action(self):
        self.login()
        token = self.csrf()
        response = self.client.post(
            "/api/v1/passport/checkin/",
            {
                "spot_id": self.sea.id,
                "lat": 35.16,
                "lng": 129.16,
                "eco_action": "plogging",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["stamp"]["eco_action"], "plogging")
        ids = [badge["id"] for badge in response.data["badges"]]
        self.assertIn("eco_1", ids)
        stamp = Passport.objects.get(user=self.user, spot=self.sea)
        self.assertEqual(stamp.eco_action, "plogging")

    def test_eco_endpoint_updates_existing_stamp(self):
        self.login()
        token = self.csrf()
        missing = self.client.post(
            "/api/v1/passport/eco/",
            {"spot_id": self.sea.id, "eco_action": "plogging"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(missing.status_code, 400)

        token = self.csrf()
        self.client.post(
            "/api/v1/passport/checkin/",
            {"spot_id": self.sea.id, "lat": 35.16, "lng": 129.16},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self.csrf()
        updated = self.client.post(
            "/api/v1/passport/eco/",
            {"spot_id": self.sea.id, "eco_action": "trash pickup"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["stamp"]["eco_action"], "trash pickup")
        ids = [badge["id"] for badge in updated.data["badges"]]
        self.assertIn("eco_1", ids)
