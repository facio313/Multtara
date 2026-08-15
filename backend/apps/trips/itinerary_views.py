from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from services.itinerary import build_itinerary
from .models import Itinerary


class ItineraryThrottle(ScopedRateThrottle):
    scope = "itinerary"


class ItinerarySerializer(serializers.Serializer):
    start_point = serializers.CharField(max_length=200)
    transport = serializers.ChoiceField(
        choices=("car", "public", "walk"),
        default="car",
        required=False,
    )
    is_day_trip = serializers.BooleanField(required=False, default=True)
    party_size = serializers.IntegerField(min_value=1, max_value=20, required=False, default=1)
    budget = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    activity = serializers.CharField(required=False, allow_blank=True, default="")


class ItineraryView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ItineraryThrottle]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "로그인이 필요합니다."}, status=401)
        rows = Itinerary.objects.filter(user=request.user).order_by("-id")[:10]
        return Response(
            [
                {
                    "id": row.id,
                    "start_point": row.start_point,
                    "transport": row.transport,
                    "is_day_trip": row.is_day_trip,
                    "party_size": row.party_size,
                    "budget": row.budget,
                    "schedule": row.schedule,
                }
                for row in rows
            ]
        )

    def post(self, request):
        serializer = ItinerarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        payload = build_itinerary(
            **serializer.validated_data,
            user=user,
            save=bool(user),
        )
        return Response(payload, status=201 if payload.get("id") else 200)
