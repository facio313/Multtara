from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conditions.models import WaterCondition
from apps.content.models import SoundProfile, SpotAnalytics, TripMemory
from apps.forecasts.models import GoldenMoment
from apps.spots.models import WaterSpot
from apps.users.models import User
from services.asmr_score import calculate_asmr_score, persist_sound_profile
from services.companion import companion_payload
from services.conditions_sync import working_condition
from services.golden_moment import find_golden_moments, persist_golden_moments
from services.spot_analytics import analytics_payload, persist_analytics
from services.water_index import upsert_scores_for_spot

STRONG = "correct-horse-battery-12"


class ExperienceServiceTests(TestCase):
    def setUp(self):
        self.sea = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산 해운대구",
            image_url="https://example.com/haeundae.jpg",
        )
        self.valley = WaterSpot.objects.create(
            type="valley",
            name="가평 용추계곡",
            lat=37.83,
            lng=127.51,
            region="경기",
            address="가평",
        )
        WaterCondition.objects.create(
            spot=self.sea,
            water_temp=24.0,
            wind_speed=4.0,
            wave_height=1.5,
            rainfall_recent=0,
            water_quality_grade="1",
            uv_index=9,
            rip_current_risk="medium",
            tide_schedule={"high_tide": ["18:50"], "low_tide": ["12:10"]},
        )
        WaterCondition.objects.create(
            spot=self.valley,
            water_temp=16.0,
            rainfall_recent=12,
            water_level=1.2,
            water_quality_grade="2",
        )
        upsert_scores_for_spot(self.sea)

    def test_asmr_score_uses_wave_and_wind(self):
        calm = calculate_asmr_score(0.2, 1.0, "sea")
        loud = calculate_asmr_score(1.8, 8.0, "sea")
        self.assertGreater(loud, calm)
        self.assertGreaterEqual(loud, 80)

    def test_sound_profile_persists(self):
        row = persist_sound_profile(self.sea)
        self.assertEqual(row.sound_type, "wave")
        self.assertEqual(SoundProfile.objects.filter(spot=self.sea).count(), 1)
        self.assertGreaterEqual(row.asmr_score, 40)

    def test_golden_overlap_within_30_minutes(self):
        rows = find_golden_moments(self.sea, days=1)
        types = {row["type"] for row in rows}
        self.assertTrue(types & {"high_tide_sunset", "sunset"})
        persist_golden_moments(self.sea)
        self.assertTrue(GoldenMoment.objects.filter(spot=self.sea).exists())

    def test_analytics_percentile_and_series(self):
        older = timezone.now() - timedelta(days=20)
        WaterCondition.objects.create(
            spot=self.sea,
            water_temp=18.0,
            water_quality_grade="2",
        )
        WaterCondition.objects.filter(spot=self.sea, water_temp=18.0).update(fetched_at=older)
        payload = analytics_payload(self.sea)
        self.assertIsNotNone(payload["avg_water_temp"])
        self.assertGreaterEqual(len(payload["series"]), 1)
        self.assertIn("headline", payload)
        persist_analytics(self.sea)
        self.assertTrue(SpotAnalytics.objects.filter(spot=self.sea).exists())

    def test_companion_warns_on_high_waves(self):
        payload = companion_payload(self.sea)
        kinds = {row["kind"] for row in payload["advice"]}
        self.assertIn("wave", kinds)
        self.assertTrue(payload["headline"])

    def test_companion_detects_rising_valley(self):
        previous = timezone.now() - timedelta(days=1)
        WaterCondition.objects.create(spot=self.valley, water_level=0.7)
        WaterCondition.objects.filter(spot=self.valley, water_level=0.7).update(fetched_at=previous)
        payload = companion_payload(self.valley)
        kinds = {row["kind"] for row in payload["advice"]}
        self.assertIn("level", kinds)

    def test_working_condition_opens_new_day_row(self):
        latest = self.sea.conditions.order_by("-fetched_at").first()
        WaterCondition.objects.filter(pk=latest.pk).update(
            fetched_at=timezone.now() - timedelta(days=1)
        )
        row = working_condition(self.sea)
        self.assertIsNone(row.pk)
        self.assertEqual(row.water_temp, latest.water_temp)


class ExperienceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="remember", password=STRONG)
        self.spot = WaterSpot.objects.create(
            type="sea",
            name="송정 해수욕장",
            lat=35.1786,
            lng=129.1996,
            region="부산",
            address="부산",
            image_url="https://example.com/songjeong.jpg",
        )
        WaterCondition.objects.create(
            spot=self.spot,
            water_temp=23.0,
            wind_speed=5.0,
            wave_height=1.3,
            water_quality_grade="1",
            tide_schedule={"high_tide": ["19:10"], "low_tide": ["12:40"]},
        )
        upsert_scores_for_spot(self.spot)

    def test_sound_and_library(self):
        detail = self.client.get(f"/api/v1/spots/{self.spot.id}/sound/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("asmr_score", detail.data)
        self.assertEqual(detail.data["playback"], "procedural")
        library = self.client.get("/api/v1/spots/sounds/")
        self.assertEqual(library.status_code, 200)
        self.assertEqual(library.data[0]["name"], "송정 해수욕장")

    def test_golden_analytics_companion_mulmung(self):
        golden = self.client.get(f"/api/v1/spots/{self.spot.id}/golden-moments/")
        self.assertEqual(golden.status_code, 200)
        self.assertTrue(isinstance(golden.data, list))
        analytics = self.client.get(f"/api/v1/spots/{self.spot.id}/analytics/")
        self.assertEqual(analytics.status_code, 200)
        self.assertIn("headline", analytics.data)
        companion = self.client.get(
            f"/api/v1/spots/{self.spot.id}/companion/",
            {"lat": 37.56, "lng": 126.97, "transport": "car"},
        )
        self.assertEqual(companion.status_code, 200)
        self.assertTrue(companion.data["advice"])
        calendar = self.client.get("/api/v1/spots/golden-calendar/")
        self.assertEqual(calendar.status_code, 200)
        mulmung = self.client.get("/api/v1/spots/mulmung/", {"mood": "static"})
        self.assertEqual(mulmung.status_code, 200)

    def test_memory_upload_and_replay(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/memories/",
            {"spot_id": self.spot.id, "photo_url": "https://example.com/then.jpg"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        memory_id = created.data["id"]
        self.assertEqual(TripMemory.objects.filter(user=self.user).count(), 1)
        replay = self.client.get(f"/api/v1/memories/{memory_id}/replay/")
        self.assertEqual(replay.status_code, 200)
        self.assertIn("vs 현재 모습", replay.data["caption"])
        self.assertEqual(replay.data["then"]["photo_url"], "https://example.com/then.jpg")
        self.assertTrue(replay.data["now"]["photo_url"])

        listed = self.client.get("/api/v1/memories/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

    def test_memory_rejects_anonymous(self):
        denied = self.client.post(
            "/api/v1/memories/",
            {"spot_id": self.spot.id},
            format="json",
        )
        self.assertEqual(denied.status_code, 401)

    @override_settings(MEDIA_ROOT="/tmp/pongdang-test-media")
    def test_memory_photo_upload(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile(
            "beach.jpg",
            b"\xff\xd8\xff\xd9",
            content_type="image/jpeg",
        )
        created = self.client.post(
            "/api/v1/memories/",
            {"spot_id": str(self.spot.id), "photo": upload},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["photo_url"].startswith("/media/memories/"))
