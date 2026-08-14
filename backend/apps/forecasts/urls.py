from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WaterForecastViewSet

router = DefaultRouter()
router.register(r'', WaterForecastViewSet, basename='waterforecast')

urlpatterns = [
    path('', include(router.urls)),
]
