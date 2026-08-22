from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.spots.models import WaterSpot
from apps.users.models import User
from apps.content.models import SoundProfile, SpotAnalytics, TripMemory

class ContentModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='river',
            name='Test River',
            lat=37.0,
            lng=127.0,
            region='Busan',
            address='456 Test Ave'
        )
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )

    def test_sound_profile_creation(self):
        sound = SoundProfile.objects.create(
            spot=self.spot,
            sound_type='waves',
            asmr_score=9.0
        )
        self.assertEqual(sound.sound_type, 'waves')

    def test_spot_analytics_creation(self):
        analytics = SpotAnalytics.objects.create(
            spot=self.spot,
            avg_water_temp_5y=18.5
        )
        self.assertEqual(analytics.avg_water_temp_5y, 18.5)

    def test_trip_memory_creation(self):
        memory = TripMemory.objects.create(
            user=self.user,
            spot=self.spot,
            taken_at=timezone.now()
        )
        self.assertEqual(memory.user.username, 'testuser')


@override_settings(PONGDANG_SSO_ENABLED=False)
class TripMemoryApiTests(TestCase):
    """Exercise the local-branch credential adapter and owner isolation."""

    def setUp(self):
        self.owner = User.objects.create_user(username="memory-owner", password="password")
        self.other = User.objects.create_user(username="memory-other", password="password")
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="Memory Beach",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Public place",
        )
        self.client = APIClient()

    def test_authentication_and_owner_isolation(self):
        memory = TripMemory.objects.create(
            user=self.owner,
            spot=self.spot,
            taken_at=timezone.now() - timedelta(days=1),
            estimated_location="해변 입구",
        )
        self.assertEqual(
            self.client.get("/api/v1/content/memories/").status_code,
            403,
        )

        self.client.force_authenticate(self.other)
        self.assertEqual(
            self.client.get(f"/api/v1/content/memories/{memory.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/v1/content/memories/").json()["results"],
            [],
        )

    def test_owner_can_create_update_and_delete_private_memory(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/content/memories/",
            {
                "spot": self.spot.pk,
                "photo_url": "https://images.example.org/trip/photo.jpg#private-fragment",
                "taken_at": (timezone.now() - timedelta(hours=1)).isoformat(),
                "estimated_location": "산책로 근처",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        memory = TripMemory.objects.get()
        self.assertEqual(memory.user, self.owner)
        self.assertEqual(memory.photo_url, "https://images.example.org/trip/photo.jpg")
        self.assertNotIn("user", response.json())

        response = self.client.patch(
            f"/api/v1/content/memories/{memory.pk}/",
            {"estimated_location": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["estimated_location"], "")

        self.assertEqual(
            self.client.delete(f"/api/v1/content/memories/{memory.pk}/").status_code,
            204,
        )

    def test_future_time_and_non_public_photo_url_are_rejected(self):
        self.client.force_authenticate(self.owner)
        for payload in (
            {
                "spot": self.spot.pk,
                "photo_url": "http://127.0.0.1/private.jpg",
                "taken_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            },
            {
                "spot": self.spot.pk,
                "photo_url": "",
                "taken_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            },
        ):
            response = self.client.post(
                "/api/v1/content/memories/",
                payload,
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(TripMemory.objects.count(), 0)

    def test_model_normalizes_links_and_api_hides_legacy_unsafe_values(self):
        with self.assertRaises(ValidationError):
            TripMemory.objects.create(
                user=self.owner,
                spot=self.spot,
                photo_url="http://127.0.0.1/private?token=secret",
                taken_at=timezone.now() - timedelta(hours=1),
            )
        memory = TripMemory.objects.create(
            user=self.owner,
            spot=self.spot,
            photo_url="https://images.example.org/memory.jpg?token=secret#private",
            taken_at=timezone.now() - timedelta(hours=1),
        )
        self.assertEqual(
            memory.photo_url,
            "https://images.example.org/memory.jpg",
        )

        # Simulate a legacy/import path that bypassed model save validation.
        TripMemory.objects.filter(pk=memory.pk).update(
            photo_url="https://user:pass@example.org/private?token=secret",
        )
        self.client.force_authenticate(self.owner)
        rendered = self.client.get(
            f"/api/v1/content/memories/{memory.pk}/"
        )

        self.assertEqual(rendered.status_code, 200)
        self.assertEqual(rendered.json()["photo_url"], "")
