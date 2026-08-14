from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from .models import ConditionScore
from .serializers import ConditionScoreSerializer

class ConditionScoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConditionScore.objects.select_related('spot').all()
    serializer_class = ConditionScoreSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['spot', 'activity']
