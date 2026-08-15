"""
PongDang (퐁당) — Root URL configuration.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse({"status": "ok", "service": "pongdang-api"})


api_v1_patterns = [
    path("auth/", include("apps.users.urls")),
    path("passport/", include("apps.users.passport_urls")),
    path("safety-card/", include("apps.trips.safety_urls")),
    path("itinerary/", include("apps.trips.itinerary_urls")),
    path("spots/", include("apps.spots.urls")),
    path("conditions/", include("apps.conditions.urls")),
    path("forecasts/", include("apps.forecasts.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
    path("api/health/", health_check),
]
