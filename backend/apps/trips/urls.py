from django.urls import path

from .views import (
    ItineraryPlanView,
    RecommendationView,
    SavedItineraryDetailView,
    SavedItineraryListView,
)


urlpatterns = [
    path("recommendations/", RecommendationView.as_view(), name="recommendations"),
    path("itineraries/plan/", ItineraryPlanView.as_view(), name="itinerary-plan"),
    path("itineraries/", SavedItineraryListView.as_view(), name="itinerary-list"),
    path(
        "itineraries/<int:pk>/",
        SavedItineraryDetailView.as_view(),
        name="itinerary-detail",
    ),
]
