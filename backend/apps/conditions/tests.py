from django.test import TestCase
from apps.spots.models import WaterSpot
from apps.conditions.models import WaterCondition, ConditionScore, CrowdLevel
from apps.conditions.views import ConditionScoreViewSet

class ConditionModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='beach',
            name='Test Beach',
            lat=37.123,
            lng=126.123,
            region='Seoul',
            address='123 Test St'
        )

    def test_water_condition_creation(self):
        condition = WaterCondition.objects.create(
            spot=self.spot,
            water_temp=20.5,
            air_temp=25.0
        )
        self.assertEqual(condition.water_temp, 20.5)

    def test_condition_score_creation(self):
        score = ConditionScore.objects.create(
            spot=self.spot,
            activity='surfing',
            score=8.5
        )
        self.assertEqual(score.activity, 'surfing')
        self.assertEqual(score.score, 8.5)

    def test_crowd_level_creation(self):
        crowd = CrowdLevel.objects.create(
            spot=self.spot,
            predicted_level='high'
        )
        self.assertEqual(crowd.predicted_level, 'high')

class ConditionViewSetTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='river',
            name='Test River API',
            lat=37.123,
            lng=126.123,
            region='Busan',
            address='123 Test St'
        )
        self.score = ConditionScore.objects.create(
            spot=self.spot,
            activity='swimming',
            score=9.0
        )

    def test_queryset_select_related(self):
        viewset = ConditionScoreViewSet()
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().activity, 'swimming')
        
        # Test that spot is fetched (using _prefetched_objects_cache or similar is hard, but we know select_related is in the query)
        self.assertIn('JOIN', str(queryset.query).upper())
