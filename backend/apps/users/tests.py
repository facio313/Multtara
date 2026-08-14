from django.test import TestCase
from apps.users.models import User, UserActivity, Passport
from apps.spots.models import WaterSpot

class UserModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='useruser',
            password='testpassword',
            persona_type='surfer'
        )
        self.spot = WaterSpot.objects.create(
            type='beach',
            name='Test Surf Beach',
            lat=34.0,
            lng=126.0,
            region='Incheon',
            address='654 Test Ln'
        )

    def test_user_creation(self):
        self.assertEqual(self.user.username, 'useruser')
        self.assertEqual(self.user.persona_type, 'surfer')

    def test_user_activity_creation(self):
        activity = UserActivity.objects.create(
            user=self.user,
            spot=self.spot,
            action='visited',
            rating=5
        )
        self.assertEqual(activity.action, 'visited')
        self.assertEqual(activity.rating, 5)

    def test_passport_creation(self):
        passport = Passport.objects.create(
            user=self.user,
            spot=self.spot,
            eco_action='picked up trash'
        )
        self.assertEqual(passport.eco_action, 'picked up trash')
