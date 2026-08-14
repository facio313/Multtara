from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WaterSpotViewSet

router = DefaultRouter()
router.register(r'', WaterSpotViewSet, basename='waterspot')

urlpatterns = [
    path('', include(router.urls)),
]
