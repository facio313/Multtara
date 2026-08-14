from django.test import TestCase
from apps.users.models import User
from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary, SafetyCard

class TripModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tripuser',
            password='testpassword'
        )
        self.spot = WaterSpot.objects.create(
            type='hotspring',
            name='Test Hotspring',
            lat=35.0,
            lng=129.0,
            region='Daegu',
            address='321 Test Blvd'
        )

    def test_itinerary_creation(self):
        itinerary = Itinerary.objects.create(
            user=self.user,
            start_point='Seoul',
            transport='train',
            is_day_trip=False,
            party_size=2
        )
        self.assertEqual(itinerary.start_point, 'Seoul')
        self.assertFalse(itinerary.is_day_trip)
        self.assertEqual(itinerary.party_size, 2)

    def test_safety_card_creation(self):
        card = SafetyCard.objects.create(
            user=self.user,
            spot=self.spot,
            risk_factors='High waves'
        )
        self.assertEqual(card.risk_factors, 'High waves')
