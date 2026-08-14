from django.test import TestCase
from apps.spots.models import WaterSpot, NearbyFacility, CatchGuide, HotspringDetail
from rest_framework.test import APIClient

class SpotModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='sea',
            name='Test Beach',
            lat=37.123,
            lng=126.123,
            region='Seoul',
            address='123 Test St'
        )

    def test_water_spot_creation(self):
        self.assertEqual(self.spot.name, 'Test Beach')
        self.assertEqual(self.spot.type, 'sea')

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
            type='sea',
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
