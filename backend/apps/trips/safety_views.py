from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.spots.models import WaterSpot
from .models import SafetyCard
from .safety import build_snapshot, card_payload, nearest_safety_facility


class SafetyCardThrottle(ScopedRateThrottle):
    scope = "safety_card"


class CreateSafetyCardSerializer(serializers.Serializer):
    spot_id = serializers.IntegerField()
    shared_with = serializers.ListField(
        child=serializers.CharField(max_length=80, allow_blank=False),
        required=False,
        max_length=8,
    )


class SafetyCardListView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SafetyCardThrottle]

    def get(self, request):
        cards = (
            SafetyCard.objects.filter(user=request.user)
            .select_related("spot")
            .order_by("-created_at")
        )
        return Response([card_payload(card) for card in cards])

    def post(self, request):
        serializer = CreateSafetyCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spot = WaterSpot.objects.filter(pk=serializer.validated_data["spot_id"]).first()
        if spot is None:
            return Response({"detail": "장소를 찾을 수 없습니다."}, status=404)
        snapshot = build_snapshot(spot)
        safety = snapshot.get("safety") or {}
        card = SafetyCard.objects.create(
            user=request.user,
            spot=spot,
            condition_snapshot=snapshot,
            risk_factors=list(safety.get("reasons") or []),
            nearest_safety_facility=nearest_safety_facility(spot),
            shared_with=list(serializer.validated_data.get("shared_with") or []),
        )
        return Response(card_payload(card), status=201)


class SafetyCardDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, card_id: int):
        card = (
            SafetyCard.objects.filter(user=request.user, pk=card_id)
            .select_related("spot")
            .first()
        )
        if card is None:
            return Response({"detail": "안전 카드를 찾을 수 없습니다."}, status=404)
        return Response(card_payload(card))
