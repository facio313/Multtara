from django.urls import path

from .safety_views import SafetyCardDetailView, SafetyCardListView

urlpatterns = [
    path("", SafetyCardListView.as_view(), name="safety-card-list"),
    path("<int:card_id>/", SafetyCardDetailView.as_view(), name="safety-card-detail"),
]
