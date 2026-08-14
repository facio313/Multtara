from django.test import TestCase
from django.utils import timezone
import datetime
from apps.spots.models import WaterSpot
from apps.forecasts.models import WaterForecast, GoldenMoment
from apps.forecasts.views import WaterForecastViewSet

class ForecastModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='valley',
            name='Test Valley',
            lat=38.0,
            lng=128.0,
            region='Jeju',
            address='789 Test Rd'
        )

    def test_water_forecast_creation(self):
        forecast = WaterForecast.objects.create(
            spot=self.spot,
            forecast_date=datetime.date.today(),
            predicted_index=4.5
        )
        self.assertEqual(forecast.predicted_index, 4.5)

    def test_golden_moment_creation(self):
        moment = GoldenMoment.objects.create(
            spot=self.spot,
            date=datetime.date.today(),
            time=datetime.time(6, 0),
            type='sunrise'
        )
        self.assertEqual(moment.type, 'sunrise')

class ForecastViewSetTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type='valley',
            name='Test Valley API',
            lat=38.0,
            lng=128.0,
            region='Jeju',
            address='789 Test Rd'
        )
        self.forecast = WaterForecast.objects.create(
            spot=self.spot,
            forecast_date=datetime.date.today(),
            predicted_index=5.0
        )

    def test_queryset_select_related(self):
        viewset = WaterForecastViewSet()
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertIn('select_related', str(queryset.query))
