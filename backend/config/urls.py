"""
PongDang (퐁당) — Root URL configuration.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from services.provider_config import get_provider_status


def health_check(request):
    return JsonResponse({"status": "ok", "service": "pongdang-api"})


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
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
    path("api/health/", health_check),
    path("api/health/integrations/", integration_health_check),
]
