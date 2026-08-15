from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.spots.models import WaterSpot, NearbyFacility, CatchGuide, HotspringDetail
from rest_framework.test import APIClient
from services.public_urls import public_https_url

class SpotModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='beach',
            name='Test Beach',
            lat=37.123,
            lng=126.123,
            region='Seoul',
            address='123 Test St'
        )

    def test_water_spot_creation(self):
        self.assertEqual(self.spot.name, 'Test Beach')
        self.assertEqual(self.spot.type, 'beach')
        self.assertEqual(self.spot.pet_policy, 'unknown')
        self.assertEqual(self.spot.accessibility_state, 'unknown')
        self.assertFalse(self.spot.age_policy_known)

    def test_structured_recommendation_evidence_validates(self):
        self.spot.preference_features = {'quiet': 0.9, 'activity_level': 0.2}
        self.spot.opening_windows = [
            {'start_minute': 540, 'end_minute': 1080},
        ]
        self.spot.age_policy_known = True
        self.spot.minimum_age = 0
        self.spot.indoor = True
        self.spot.bad_weather_suitable = True
        self.spot.catalog_confidence = 0.85
        self.spot.full_clean()

    def test_unknown_or_invalid_catalog_evidence_fails_validation(self):
        self.spot.preference_features = {'quiet': 1.2}
        self.spot.opening_windows = [{'start_minute': 800, 'end_minute': 700}]
        self.spot.age_policy_known = True
        self.spot.minimum_age = None
        self.spot.bad_weather_suitable = True
        self.spot.indoor = False

        with self.assertRaises(ValidationError) as raised:
            self.spot.full_clean()

        self.assertIn('preference_features', raised.exception.message_dict)
        self.assertIn('opening_windows', raised.exception.message_dict)
        self.assertIn('minimum_age', raised.exception.message_dict)
        self.assertIn('bad_weather_suitable', raised.exception.message_dict)

    def test_blank_curated_provider_identifiers_can_repeat(self):
        second = WaterSpot.objects.create(
            type='beach',
            name='Second Unlinked Beach',
            lat=37.2,
            lng=126.2,
            tourapi_id='',
            khoa_beach_code='',
            region='Seoul',
            address='456 Test St',
        )

        self.assertEqual(self.spot.tourapi_id, '')
        self.assertEqual(second.tourapi_id, '')
        self.assertEqual(WaterSpot.objects.filter(tourapi_id='').count(), 2)

    def test_duplicate_nonblank_tourapi_id_is_rejected_by_database(self):
        self.spot.tourapi_id = 'tour-duplicate'
        self.spot.save(update_fields=('tourapi_id',))

        with self.assertRaises(IntegrityError), transaction.atomic():
            WaterSpot.objects.create(
                type='beach',
                name='Duplicate TourAPI Beach',
                lat=37.2,
                lng=126.2,
                tourapi_id='tour-duplicate',
                region='Seoul',
                address='456 Test St',
            )

    def test_duplicate_nonblank_khoa_beach_code_is_rejected_by_database(self):
        self.spot.khoa_beach_code = 'KHOA-DUPLICATE'
        self.spot.save(update_fields=('khoa_beach_code',))

        with self.assertRaises(IntegrityError), transaction.atomic():
            WaterSpot.objects.create(
                type='beach',
                name='Duplicate KHOA Beach',
                lat=37.2,
                lng=126.2,
                khoa_beach_code='KHOA-DUPLICATE',
                region='Seoul',
                address='456 Test St',
            )

    def test_nearby_facility_creation(self):
        facility = NearbyFacility.objects.create(
            spot=self.spot,
            type='parking',
            name='Test Parking',
            lat=37.124,
            lng=126.124,
            distance_min=5
        )
        self.assertEqual(facility.name, 'Test Parking')

    def test_catch_guide_creation(self):
        guide = CatchGuide.objects.create(
            spot=self.spot,
            species='Salmon'
        )
        self.assertEqual(guide.species, 'Salmon')

    def test_hotspring_detail_creation(self):
        detail = HotspringDetail.objects.create(
            spot=self.spot,
            minerals='Sulfur'
        )
        self.assertEqual(detail.minerals, 'Sulfur')

from apps.spots.views import WaterSpotViewSet

class SpotViewTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='beach',
            name='Test Beach API',
            lat=37.123,
            lng=126.123,
            region='Seoul',
            address='123 Test St'
        )

    def test_waterspot_queryset(self):
        viewset = WaterSpotViewSet()
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().name, 'Test Beach API')

    def test_public_serializer_is_allowlisted_and_strips_url_credentials(self):
        self.spot.preference_features = {"internal_rank_weight": 0.9}
        self.spot.image_url = "https://images.example.com/photo.jpg?token=private#fragment"
        self.spot.livecam_url = "https://user:password@camera.example.com/live"
        self.spot.catalog_source_url = "https://www.data.go.kr/data/15101578/openapi.do?serviceKey=private"
        self.spot.save()

        response = APIClient().get("/api/v1/spots/")

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertNotIn("preference_features", item)
        self.assertEqual(item["image_url"], "https://images.example.com/photo.jpg")
        self.assertEqual(item["livecam_url"], "")
        self.assertEqual(
            item["catalog_source_url"],
            "https://www.data.go.kr/data/15101578/openapi.do",
        )


class PublicUrlTests(TestCase):
    def test_public_https_url_rejects_local_or_non_https_destinations(self):
        self.assertEqual(public_https_url("http://example.com/image.jpg"), "")
        self.assertEqual(public_https_url("https://127.0.0.1/private"), "")
        self.assertEqual(public_https_url("https://service.internal/private"), "")
        self.assertEqual(public_https_url("https://example.com:8443/private"), "")
