from django.urls import path

from .memory_views import MemoryDetailView, MemoryListView, MemoryReplayView

urlpatterns = [
    path("", MemoryListView.as_view(), name="memory-list"),
    path("<int:memory_id>/", MemoryDetailView.as_view(), name="memory-detail"),
    path("<int:memory_id>/replay/", MemoryReplayView.as_view(), name="memory-replay"),
]
