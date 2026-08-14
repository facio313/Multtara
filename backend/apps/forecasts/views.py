from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from .models import WaterForecast
from .serializers import WaterForecastSerializer

class WaterForecastViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WaterForecast.objects.select_related('spot').all()
    serializer_class = WaterForecastSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['spot']
