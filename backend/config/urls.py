"""
PongDang (퐁당) — Root URL configuration.
"""

from collections import Counter

from django.conf import settings
from django.contrib import admin
from django.db import DatabaseError, connection
from django.utils import timezone
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from services.provider_config import get_provider_status
from services.provider_config import ProviderConfig
from services.pipeline_health import pipeline_health_report
from services.safety_readiness import audit_safety_readiness
from apps.spots.models import WaterSpot


@require_GET
def health_check(request):
    return JsonResponse({"status": "ok", "service": "pongdang-api"})


@require_GET
def readiness_check(request):
    """Report whether the API can serve requests that require its database.

    Liveness deliberately stays independent of downstream services. Container
    orchestration uses this separate readiness endpoint so a running Gunicorn
    process is not mistaken for a usable application while PostgreSQL is down.
    Exception details are never returned to clients.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {"status": "unavailable", "service": "pongdang-api"},
            status=503,
        )
    return JsonResponse({"status": "ready", "service": "pongdang-api"})


@require_GET
def integration_health_check(request):
    try:
        report, healthy = pipeline_health_report(
            at=timezone.now(),
            config=ProviderConfig.from_environment(),
        )
    except DatabaseError:
        report = {"status": "degraded", "detail": "pipeline state unavailable"}
        healthy = False
    provider_status = get_provider_status()
    return JsonResponse(
        {
            **report,
            "service": "pongdang-integrations",
            "configured_count": sum(
                1 for enabled in provider_status.values() if enabled
            ),
        },
        status=200 if healthy else 503,
    )


@require_GET
def safety_readiness_health_check(request):
    """Expose bounded aggregates, never a fabricated safety-clearance claim."""

    try:
        spots = tuple(
            WaterSpot.objects.filter(catalog_verification="verified")
            .exclude(catalog_source="PONGDANG_DEMO")
            .order_by("pk")[:501]
        )
        if not spots or len(spots) > 500:
            return JsonResponse(
                {
                    "status": "degraded",
                    "service": "pongdang-safety-readiness",
                    "detail": (
                        "no verified catalog spots"
                        if not spots
                        else "audit scope exceeds 500 spots"
                    ),
                },
                status=503,
            )
        report = audit_safety_readiness(at=timezone.now(), spots=spots)
    except DatabaseError:
        return JsonResponse(
            {
                "status": "degraded",
                "service": "pongdang-safety-readiness",
                "detail": "safety readiness state unavailable",
            },
            status=503,
        )
    reasons = Counter(
        reason
        for entry in report.entries
        for reason in entry.reason_codes
    )
    healthy = report.current_clear_count > 0
    return JsonResponse(
        {
            "status": "ok" if healthy else "degraded",
            "service": "pongdang-safety-readiness",
            "checked_at": report.checked_at,
            "spots": len(spots),
            "evaluations": len(report.entries),
            "counts": report.counts,
            "reason_counts": dict(sorted(reasons.items())),
        },
        status=200 if healthy else 503,
    )


api_v1_patterns = [
    path("users/", include("apps.users.urls")),
    path("content/", include("apps.content.urls")),
    path("spots/", include("apps.spots.urls")),
    path("conditions/", include("apps.conditions.urls")),
    path("forecasts/", include("apps.forecasts.urls")),
    path("trips/", include("apps.trips.urls")),
]

urlpatterns = [
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
    path("api/health/", health_check),
    path("api/health/ready/", readiness_check),
    path("api/health/integrations/", integration_health_check),
    path("api/health/safety/", safety_readiness_health_check),
]

if not settings.PONGDANG_SSO_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
