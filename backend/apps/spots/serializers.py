from rest_framework import serializers

from services.public_urls import public_https_url

from .models import WaterSpot


class WaterSpotSerializer(serializers.ModelSerializer):
    livecam_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    catalog_source_url = serializers.SerializerMethodField()

    class Meta:
        model = WaterSpot
        fields = (
            "id",
            "type",
            "name",
            "lat",
            "lng",
            "tourapi_id",
            "khoa_beach_code",
            "tags",
            "livecam_url",
            "pet_allowed",
            "pet_policy",
            "accessibility",
            "accessibility_state",
            "region",
            "address",
            "image_url",
            "description",
            "opening_windows",
            "typical_duration_minutes",
            "cost_krw",
            "age_policy_known",
            "minimum_age",
            "maximum_age",
            "indoor",
            "bad_weather_suitable",
            "catalog_confidence",
            "catalog_verification",
            "catalog_source",
            "catalog_source_url",
            "catalog_verified_at",
        )
        read_only_fields = fields

    def get_livecam_url(self, spot: WaterSpot) -> str:
        return public_https_url(spot.livecam_url)

    def get_image_url(self, spot: WaterSpot) -> str:
        return public_https_url(spot.image_url)

    def get_catalog_source_url(self, spot: WaterSpot) -> str:
        return public_https_url(spot.catalog_source_url)
