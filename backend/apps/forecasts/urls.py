from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyForecastListView, WaterForecastViewSet

router = DefaultRouter()
router.register(r'', WaterForecastViewSet, basename='waterforecast')

urlpatterns = [
    path("daily/", DailyForecastListView.as_view(), name="daily-forecast-list"),
    path('', include(router.urls)),
]
