from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.spots.models import WaterSpot
from .models import Passport, UserActivity
from .stamps import passport_payload, stamp_payload, within_checkin_range


class CheckinThrottle(ScopedRateThrottle):
    scope = "passport_checkin"


class CheckinSerializer(serializers.Serializer):
    spot_id = serializers.IntegerField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class PassportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(passport_payload(request.user))


class PassportBadgesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = passport_payload(request.user)
        return Response(payload["badges"])


class PassportCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = passport_payload(request.user)
        return Response(payload["collection"])


class PassportCheckinView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [CheckinThrottle]

    def post(self, request):
        serializer = CheckinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spot = WaterSpot.objects.filter(pk=serializer.validated_data["spot_id"]).first()
        if spot is None:
            return Response({"detail": "장소를 찾을 수 없습니다."}, status=404)
        if Passport.objects.filter(user=request.user, spot=spot).exists():
            return Response({"detail": "이미 인증한 장소입니다."}, status=400)
        if not within_checkin_range(
            spot,
            serializer.validated_data["lat"],
            serializer.validated_data["lng"],
        ):
            return Response({"detail": "이 장소 근처에서만 인증할 수 있습니다."}, status=400)
        stamp = Passport.objects.create(user=request.user, spot=spot)
        UserActivity.objects.create(user=request.user, spot=spot, action="visited")
        payload = passport_payload(request.user)
        payload["stamp"] = stamp_payload(stamp)
        return Response(payload, status=201)
