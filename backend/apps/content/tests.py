from django.test import TestCase
from django.utils import timezone
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
