from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from services.daily_forecasts import (
    ACTIVITY_NOT_SUPPORTED_FOR_SPOT,
    DAILY_FORECAST_METHODOLOGY_VERSION,
    DAILY_REFERENCE_TIME,
    KST,
    PROVIDER_HORIZON_UNAVAILABLE,
)
from services.ingestion.fusion import activity_supported_for_spot
from services.water_index import (
    Activity,
    METHODOLOGY_VERSION,
    SURF_SKILL_LEVEL_REQUIRED,
)

from .models import DailyForecast, WaterForecast
from .serializers import (
    DailyForecastQuerySerializer,
    WaterForecastSerializer,
    daily_forecast_payload,
)


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


class DailyForecastListView(APIView):
    """Return exactly one fail-closed projection for each requested date."""

    def get(self, request, *args, **kwargs):
        as_of = timezone.now()
        query = DailyForecastQuerySerializer(
            data=request.query_params,
            context={"as_of": as_of},
        )
        query.is_valid(raise_exception=True)
        values = query.validated_data
        spot = values["spot"]
        activity = Activity(values["activity"])
        participant_profile = values["participant_profile"]
        participant_skill_level = values["participant_skill_level"]
        start_date = values.get("start_date") or timezone.localdate(as_of)
        days = values["days"]
        dates = tuple(start_date + timedelta(days=offset) for offset in range(days))

        rows = (
            DailyForecast.objects.select_related("spot")
            .filter(
                spot=spot,
                activity=activity.value,
                participant_profile=participant_profile,
                participant_skill_level=participant_skill_level,
                forecast_date__in=dates,
                evaluated_at__lte=as_of,
            )
            .order_by("forecast_date", "-evaluated_at", "-id")
        )
        latest_by_date: dict = {}
        for row in rows:
            latest_by_date.setdefault(row.forecast_date, row)

        supported = activity_supported_for_spot(spot, activity)
        results = []
        for forecast_date in dates:
            row = latest_by_date.get(forecast_date)
            if row is not None:
                results.append(daily_forecast_payload(row, as_of=as_of))
                continue
            reason = (
                ACTIVITY_NOT_SUPPORTED_FOR_SPOT
                if not supported
                else SURF_SKILL_LEVEL_REQUIRED
                if activity is Activity.SURF
                and participant_skill_level == "unspecified"
                else PROVIDER_HORIZON_UNAVAILABLE
            )
            results.append(
                _missing_forecast_payload(
                    spot=spot,
                    forecast_date=forecast_date,
                    activity=activity,
                    participant_profile=participant_profile,
                    participant_skill_level=participant_skill_level,
                    reason=reason,
                )
            )

        return Response(
            {
                "count": len(results),
                "spot": spot.pk,
                "spot_name": spot.name,
                "activity": activity.value,
                "participant_profile": participant_profile,
                "participant_skill_level": participant_skill_level,
                "start_date": start_date,
                "days": days,
                "reference_time": DAILY_REFERENCE_TIME.isoformat(),
                "methodology_version": METHODOLOGY_VERSION,
                "projection_methodology_version": (
                    DAILY_FORECAST_METHODOLOGY_VERSION
                ),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


def _missing_forecast_payload(
    *,
    spot,
    forecast_date,
    activity: Activity,
    participant_profile: str,
    participant_skill_level: str,
    reason: str,
) -> dict:
    target_at = datetime.combine(forecast_date, DAILY_REFERENCE_TIME, tzinfo=KST)
    return {
        "id": None,
        "spot": spot.pk,
        "spot_name": spot.name,
        "forecast_date": forecast_date,
        "activity": activity.value,
        "participant_profile": participant_profile,
        "participant_skill_level": participant_skill_level,
        "target_at": target_at,
        "score": None,
        "suitability_score": None,
        "safety_status": "unknown",
        "decision": "unknown",
        "confidence": 0.0,
        "coverage": 0.0,
        "score_range": [],
        "gates": [
            {
                "rule_id": "forecast.evidence.available",
                "severity": "unknown",
                "metric_name": "forecast_evidence",
                "reason_code": reason,
            }
        ],
        "contributions": [],
        "missing_metrics": ["forecast_evidence"],
        "stale_or_conflicting_metrics": [],
        "limitations": [],
        "availability": "unavailable",
        "unavailable_reason": reason,
        "providers": [],
        "evidence_issued_at": None,
        "evidence_fetched_at": None,
        "valid_from": target_at,
        "valid_until": target_at,
        "methodology_version": METHODOLOGY_VERSION,
        "projection_methodology_version": DAILY_FORECAST_METHODOLOGY_VERSION,
        "evaluated_at": None,
        "computed_at": None,
        "updated_at": None,
        "evidence": [],
    }
