from django.conf import settings
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend

from .models import WaterForecast
from .serializers import WaterForecastSerializer


class WaterForecastViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WaterForecast.objects.select_related("spot").all()
    serializer_class = WaterForecastSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["spot"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not getattr(settings, "PUBLIC_LEGACY_WATER_FORECASTS", True):
            return queryset.none()
        return queryset
