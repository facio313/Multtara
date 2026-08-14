from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConditionScoreViewSet

router = DefaultRouter()
router.register(r'scores', ConditionScoreViewSet, basename='conditionscore')

urlpatterns = [
    path('', include(router.urls)),
]
