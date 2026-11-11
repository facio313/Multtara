import datetime

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.forecasts.models import WaterForecast, GoldenMoment
from apps.forecasts.views import WaterForecastViewSet
from apps.spots.models import WaterSpot


class ForecastModelTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type="valley",
            name="Test Valley",
            lat=38.0,
            lng=128.0,
            region="Jeju",
            address="789 Test Rd",
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
            type="sunrise",
        )
        self.assertEqual(moment.type, "sunrise")


class ForecastViewSetTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type="valley",
            name="Test Valley API",
            lat=38.0,
            lng=128.0,
            region="Jeju",
            address="789 Test Rd",
        )
        self.forecast = WaterForecast.objects.create(
            spot=self.spot,
            forecast_date=datetime.date.today(),
            predicted_index=5.0
        )

    @override_settings(PUBLIC_LEGACY_WATER_FORECASTS=True)
    def test_queryset_select_related(self):
        viewset = WaterForecastViewSet()
        queryset = viewset.get_queryset()
        self.assertEqual(queryset.count(), 1)

        with self.assertNumQueries(1):
            forecast = queryset.get()
            self.assertEqual(forecast.spot.name, "Test Valley API")

    @override_settings(PUBLIC_LEGACY_WATER_FORECASTS=False)
    def test_production_gate_returns_an_empty_list_even_when_rows_exist(self):
        request = APIRequestFactory().get("/api/v1/forecasts/")

        response = WaterForecastViewSet.as_view({"get": "list"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    @override_settings(PUBLIC_LEGACY_WATER_FORECASTS=False)
    def test_production_gate_hides_existing_detail_rows(self):
        request = APIRequestFactory().get(
            f"/api/v1/forecasts/{self.forecast.pk}/"
        )

        response = WaterForecastViewSet.as_view({"get": "retrieve"})(
            request,
            pk=self.forecast.pk,
        )

        self.assertEqual(response.status_code, 404)

    def test_legacy_forecast_read_api_is_fail_closed_by_default(self):
        request = APIRequestFactory().get("/api/v1/forecasts/")

        response = WaterForecastViewSet.as_view({"get": "list"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])
