from django.urls import path

from .passport_views import (
    PassportBadgesView,
    PassportCheckinView,
    PassportCollectionView,
    PassportView,
)

urlpatterns = [
    path("", PassportView.as_view(), name="passport"),
    path("checkin/", PassportCheckinView.as_view(), name="passport-checkin"),
    path("badges/", PassportBadgesView.as_view(), name="passport-badges"),
    path("collection/", PassportCollectionView.as_view(), name="passport-collection"),
]
