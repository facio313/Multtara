from __future__ import annotations

from rest_framework import serializers

from apps.spots.models import WaterSpot
from services.ingestion.fusion import environment_for_spot_type
from services.recommendation import ParticipantSkillLevel
from services.water_index import Activity
from services.water_index import supports_activity_environment


MAX_PREFERENCES = 20


class PreferenceTargetInputSerializer(serializers.Serializer):
    feature = serializers.CharField(max_length=64)
    target = serializers.FloatField(min_value=0.0, max_value=1.0)
    weight = serializers.FloatField(min_value=0.01, max_value=100.0, default=1.0)


class PartyInputSerializer(serializers.Serializer):
    ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=120),
        min_length=1,
        max_length=12,
    )
    requires_accessibility = serializers.BooleanField(default=False)
    bringing_pet = serializers.BooleanField(default=False)
    adult_supervision_confirmed = serializers.BooleanField(
        required=False,
        allow_null=True,
        default=None,
    )
    participant_skill_level = serializers.ChoiceField(
        choices=[level.value for level in ParticipantSkillLevel],
        default=ParticipantSkillLevel.UNSPECIFIED.value,
    )


class RecommendationInputSerializer(serializers.Serializer):
    activity = serializers.ChoiceField(choices=[activity.value for activity in Activity])
    preferences = PreferenceTargetInputSerializer(
        many=True,
        max_length=MAX_PREFERENCES,
    )
    party = PartyInputSerializer()
    persona_label = serializers.CharField(
        max_length=50,
        allow_blank=True,
        required=False,
        default="",
    )
    region = serializers.CharField(max_length=100, required=False, allow_blank=False)
    spot_type = serializers.ChoiceField(
        choices=WaterSpot.SpotType.values,
        required=False,
    )
    limit = serializers.IntegerField(min_value=1, max_value=12, default=6)

    def validate_preferences(self, value):
        if not value:
            raise serializers.ValidationError("At least one preference is required.")
        canonical = [
            "_".join(item["feature"].strip().lower().replace("-", " ").split())
            for item in value
        ]
        if any(not name for name in canonical):
            raise serializers.ValidationError("Preference names cannot be blank.")
        if len(canonical) != len(set(canonical)):
            raise serializers.ValidationError("Preference names must be unique.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        spot_type = attrs.get("spot_type")
        if spot_type and not supports_activity_environment(
            Activity(attrs["activity"]),
            environment_for_spot_type(spot_type),
        ):
            raise serializers.ValidationError(
                {
                    "spot_type": (
                        "The requested activity is not supported for this spot type."
                    )
                }
            )
        return attrs
