"""
PongDang (퐁당) — Root URL configuration.
"""

from django.contrib import admin
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from services.provider_config import get_provider_status


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
    return JsonResponse(
        {
            "status": "ok",
            "service": "pongdang-integrations",
            "configured": get_provider_status(),
        }
    )


api_v1_patterns = [
    path("spots/", include("apps.spots.urls")),
    path("conditions/", include("apps.conditions.urls")),
    path("forecasts/", include("apps.forecasts.urls")),
    path("trips/", include("apps.trips.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
    path("api/health/", health_check),
    path("api/health/ready/", readiness_check),
    path("api/health/integrations/", integration_health_check),
]
