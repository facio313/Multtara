from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from .models import WaterSpot
from .serializers import WaterSpotSerializer

class WaterSpotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WaterSpot.objects.all()
    serializer_class = WaterSpotSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['type', 'region']
