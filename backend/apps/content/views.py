from __future__ import annotations

from rest_framework import generics, permissions, throttling

from .models import TripMemory
from .serializers import TripMemorySerializer


class MemoryWriteThrottle(throttling.UserRateThrottle):
    rate = "30/hour"


class MemoryWriteThrottleMixin:
    def get_throttles(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [MemoryWriteThrottle()]
        return super().get_throttles()


class TripMemoryListCreateView(MemoryWriteThrottleMixin, generics.ListCreateAPIView):
    serializer_class = TripMemorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return (
            TripMemory.objects.filter(user=self.request.user)
            .select_related("spot")
            .order_by("-taken_at", "-id")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TripMemoryDetailView(
    MemoryWriteThrottleMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = TripMemorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return TripMemory.objects.filter(user=self.request.user).select_related("spot")
