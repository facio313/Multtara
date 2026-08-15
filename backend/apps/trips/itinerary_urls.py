from django.urls import path

from .itinerary_views import ItineraryView

urlpatterns = [
    path("", ItineraryView.as_view(), name="itinerary"),
]
