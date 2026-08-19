from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.content.models import TripMemory
from apps.spots.models import WaterSpot
from services.memory_replay import memory_payload, record_memory, replay_payload, save_photo


class MemoryThrottle(ScopedRateThrottle):
    scope = "memories"


class MemoryCreateSerializer(serializers.Serializer):
    spot_id = serializers.IntegerField()
    photo_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    estimated_location = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class MemoryListView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [MemoryThrottle]

    def get(self, request):
        rows = (
            TripMemory.objects.filter(user=request.user)
            .select_related("spot")
            .order_by("-taken_at")
        )
        return Response([memory_payload(row) for row in rows])

    def post(self, request):
        serializer = MemoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spot = WaterSpot.objects.filter(pk=serializer.validated_data["spot_id"]).first()
        if spot is None:
            return Response({"detail": "장소를 찾을 수 없습니다."}, status=404)
        photo_url = (serializer.validated_data.get("photo_url") or "").strip()
        upload = request.FILES.get("photo")
        if upload:
            try:
                photo_url = save_photo(upload, request.user.id)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
        row = record_memory(
            request.user,
            spot,
            photo_url=photo_url,
            estimated_location=serializer.validated_data.get("estimated_location") or "",
        )
        return Response(memory_payload(row), status=201)


class MemoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, memory_id: int):
        row = (
            TripMemory.objects.filter(user=request.user, pk=memory_id)
            .select_related("spot")
            .first()
        )
        if row is None:
            return Response({"detail": "추억을 찾을 수 없습니다."}, status=404)
        return Response(memory_payload(row))


class MemoryReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, memory_id: int):
        row = (
            TripMemory.objects.filter(user=request.user, pk=memory_id)
            .select_related("spot")
            .first()
        )
        if row is None:
            return Response({"detail": "추억을 찾을 수 없습니다."}, status=404)
        return Response(replay_payload(row))
