from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConditionScoreViewSet, ObservationSnapshotViewSet

router = DefaultRouter()
router.register(r'scores', ConditionScoreViewSet, basename='conditionscore')
router.register(r'observations', ObservationSnapshotViewSet, basename='observation')

urlpatterns = [
    path('', include(router.urls)),
]
