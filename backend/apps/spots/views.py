import math

from django.db.models import Avg, OuterRef, Prefetch, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.conditions.models import ConditionScore, CrowdLevel, WaterCondition
from apps.conditions.serializers import ConditionScoreSerializer, WaterConditionSerializer
from apps.forecasts.models import WaterForecast
from apps.forecasts.serializers import WaterForecastSerializer
from services.concierge import concierge_spots
from services.recommend import recommend_spots
from services.spot_extras import quality_trust as quality_trust_payload
from .models import WaterSpot
from .serializers import WaterSpotSerializer

ACTIVITY_SPOT_TYPES = {
    "swim": ("sea", "pool", "waterpark"),
    "surf": ("sea",),
    "relax": ("lake", "valley", "waterfall", "sea"),
    "mudflat": ("tidal_flat",),
    "onsen": ("hotspring",),
    "rafting": ("riverside", "valley"),
}


class SpotPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


def _haversine_km(lat1, lng1, lat2, lng2):
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class WaterSpotViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WaterSpotSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["type", "region", "pet_allowed"]
    pagination_class = SpotPagination

    def get_queryset(self):
        return (
            WaterSpot.objects.all()
            .select_related("hotspringdetail")
            .prefetch_related(
                Prefetch("scores", queryset=ConditionScore.objects.order_by("-computed_at")),
                Prefetch("conditions", queryset=WaterCondition.objects.order_by("-fetched_at")),
                Prefetch("crowd_levels", queryset=CrowdLevel.objects.order_by("-updated_at")),
                "nearbyfacility_set",
                "catchguide_set",
            )
            .order_by("id")
        )

    @action(detail=True, methods=["get"])
    def condition(self, request, pk=None):
        spot = self.get_object()
        latest = spot.conditions.order_by("-fetched_at").first()
        if latest is None:
            return Response({"detail": "No condition recorded."}, status=404)
        return Response(WaterConditionSerializer(latest).data)

    @action(detail=True, methods=["get"])
    def scores(self, request, pk=None):
        spot = self.get_object()
        rows = ConditionScore.objects.filter(spot=spot).order_by("activity", "-computed_at")
        latest = {}
        for row in rows:
            latest.setdefault(row.activity, row)
        return Response(ConditionScoreSerializer(list(latest.values()), many=True).data)

    @action(detail=True, methods=["get"])
    def forecast(self, request, pk=None):
        spot = self.get_object()
        rows = WaterForecast.objects.filter(spot=spot).order_by("forecast_date")
        return Response(WaterForecastSerializer(rows, many=True).data)

    @action(detail=False, methods=["get"])
    def ranking(self, request):
        activity = request.query_params.get("activity", "swim")
        latest_score = (
            ConditionScore.objects.filter(spot=OuterRef("pk"), activity=activity)
            .order_by("-computed_at")
            .values("score")[:1]
        )
        queryset = self.filter_queryset(self.get_queryset()).annotate(
            annotated_index=Subquery(latest_score)
        )
        allowed_types = ACTIVITY_SPOT_TYPES.get(activity)
        if allowed_types:
            queryset = queryset.filter(type__in=allowed_types)
        queryset = queryset.filter(annotated_index__isnull=False).order_by(
            "-annotated_index", "id"
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def recommend(self, request):
        user = request.user if request.user.is_authenticated else None
        payload = recommend_spots(self.filter_queryset(self.get_queryset()), user)
        spots = payload["spots"]
        page = self.paginate_queryset(spots)
        serializer = self.get_serializer(
            page if page is not None else spots,
            many=True,
            context={"request": request, "activity": payload["activity"]},
        )
        meta = {
            "personalized": payload["personalized"],
            "activity": payload["activity"],
            "persona_type": payload["persona_type"],
            "mood_state": payload["mood_state"],
            "home_region": payload["home_region"],
            "reason": payload["reason"],
        }
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.data = {**meta, **response.data}
            return response
        return Response({**meta, "results": serializer.data})

    @action(detail=False, methods=["get"])
    def concierge(self, request):
        query = request.query_params.get("q", "")
        user = request.user if request.user.is_authenticated else None
        payload = concierge_spots(query, user)
        spots = payload["spots"]
        page = self.paginate_queryset(spots)
        serializer = self.get_serializer(
            page if page is not None else spots,
            many=True,
            context={"request": request, "activity": payload["activity"]},
        )
        meta = {
            "personalized": payload["personalized"],
            "activity": payload["activity"],
            "persona_type": payload["persona_type"],
            "mood_state": payload["mood_state"],
            "home_region": payload["home_region"],
            "reason": payload["reason"],
            "parsed": payload["parsed"],
        }
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.data = {**meta, **response.data}
            return response
        return Response({**meta, "results": serializer.data})

    @action(detail=True, methods=["get"], url_path="quality-trust")
    def quality_trust(self, request, pk=None):
        return Response(quality_trust_payload(self.get_object()))

    @action(detail=False, methods=["get"])
    def nearby(self, request):
        try:
            lat = float(request.query_params.get("lat"))
            lng = float(request.query_params.get("lng"))
        except (TypeError, ValueError):
            return Response({"detail": "lat and lng are required."}, status=400)
        try:
            radius = float(request.query_params.get("radius", 80))
        except ValueError:
            radius = 80

        matches = []
        for spot in self.filter_queryset(self.get_queryset()):
            distance = _haversine_km(lat, lng, spot.lat, spot.lng)
            if distance <= radius:
                matches.append((distance, spot))
        matches.sort(key=lambda item: item[0])
        spots = [spot for _distance, spot in matches[:50]]
        return Response(self.get_serializer(spots, many=True).data)

    @action(detail=False, methods=["get"], url_path="forecast-summary")
    def forecast_summary(self, request):
        region = request.query_params.get("region")
        rows = WaterForecast.objects.all()
        if region and region != "전국":
            rows = rows.filter(spot__region=region)
        grouped = list(
            rows.values("forecast_date")
            .annotate(predicted_index=Avg("predicted_index"))
            .order_by("forecast_date")
        )
        if not grouped:
            return Response({"days": [], "message": "예보 데이터가 없습니다."})

        best = max(grouped, key=lambda row: row["predicted_index"] or 0)
        weekday = ["월", "화", "수", "목", "금", "토", "일"][best["forecast_date"].weekday()]
        message = (
            f"{best['forecast_date'].month}/{best['forecast_date'].day} "
            f"({weekday}) 방문을 추천합니다."
        )
        payload = []
        for row in grouped:
            payload.append(
                {
                    "forecast_date": row["forecast_date"],
                    "predicted_index": round(row["predicted_index"] or 0),
                }
            )
        source = "kma" if rows.filter(predicted_factors__source="kma").exists() else "stored"
        return Response(
            {
                "days": payload,
                "message": message,
                "best_date": best["forecast_date"],
                "source": source,
            }
        )

    @action(detail=False, methods=["get"])
    def livecams(self, request):
        queryset = self.filter_queryset(self.get_queryset()).exclude(livecam_url="")
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="first-swim")
    def first_swim(self, request):
        try:
            threshold = float(request.query_params.get("threshold", 22.5))
        except ValueError:
            threshold = 22.5
        latest_temp = (
            WaterCondition.objects.filter(spot=OuterRef("pk"))
            .order_by("-fetched_at")
            .values("water_temp")[:1]
        )
        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(type="sea")
            .annotate(latest_water_temp=Subquery(latest_temp))
            .filter(latest_water_temp__gte=threshold)
            .order_by("-latest_water_temp")
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="safety-radar")
    def safety_radar(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(
            type__in=("valley", "riverside", "waterfall", "sea")
        )
        serializer = self.get_serializer(queryset, many=True)
        order = {"danger": 0, "caution": 1, "safe": 2}
        rows = sorted(
            serializer.data,
            key=lambda row: (order.get((row.get("safety") or {}).get("level"), 9), row["name"]),
        )
        return Response(rows)
