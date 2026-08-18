from django.urls import path

from .views import TripMemoryDetailView, TripMemoryListCreateView


urlpatterns = [
    path("memories/", TripMemoryListCreateView.as_view(), name="memory-list"),
    path("memories/<int:pk>/", TripMemoryDetailView.as_view(), name="memory-detail"),
]
