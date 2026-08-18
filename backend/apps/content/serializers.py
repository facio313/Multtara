from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.spots.serializers import WaterSpotSerializer
from services.public_urls import public_https_url

from .models import TripMemory


class TripMemorySerializer(serializers.ModelSerializer):
    spot_detail = WaterSpotSerializer(source="spot", read_only=True)
    photo_url = serializers.CharField(required=False, allow_blank=True, max_length=200)

    class Meta:
        model = TripMemory
        fields = (
            "id",
            "spot",
            "spot_detail",
            "photo_url",
            "taken_at",
            "estimated_location",
        )
        read_only_fields = ("id", "spot_detail")

    def validate_photo_url(self, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            return ""
        safe = public_https_url(candidate)
        if not safe:
            raise serializers.ValidationError(
                "Photo URL must be a public HTTPS URL without credentials."
            )
        return safe

    def validate_taken_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("taken_at cannot be in the future.")
        return value

    def validate_estimated_location(self, value: str) -> str:
        # This free-form label remains private to the owning account. Reject
        # control characters so it is safe to render and export.
        candidate = value.strip()
        if any(ord(char) < 32 for char in candidate):
            raise serializers.ValidationError("Location label contains invalid characters.")
        return candidate

    def to_representation(self, instance: TripMemory) -> dict:
        representation = super().to_representation(instance)
        # Treat database rows as untrusted too: a legacy/imported value may
        # have bypassed serializer and model validation.
        representation["photo_url"] = public_https_url(instance.photo_url)
        return representation
