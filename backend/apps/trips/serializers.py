from __future__ import annotations

from datetime import timedelta

from rest_framework import serializers
from django.utils import timezone

from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary, TransportMode
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


class ItineraryPlanInputSerializer(serializers.Serializer):
    recommendation = RecommendationInputSerializer()
    candidate_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=12,
        required=False,
    )
    start_spot = serializers.PrimaryKeyRelatedField(
        queryset=WaterSpot.objects.all(),
    )
    end_spot = serializers.PrimaryKeyRelatedField(
        queryset=WaterSpot.objects.all(),
    )
    transport = serializers.ChoiceField(choices=TransportMode.values)
    plan_date = serializers.DateField()
    start_minute = serializers.IntegerField(min_value=0, max_value=1_439)
    end_minute = serializers.IntegerField(min_value=1, max_value=1_440)
    budget_krw = serializers.IntegerField(min_value=0, max_value=100_000_000)
    bad_weather = serializers.BooleanField(default=False)
    save = serializers.BooleanField(default=False)
    title = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_candidate_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Candidate ids must be unique.")
        return value

    def validate_start_spot(self, value):
        if value.catalog_verification == WaterSpot.VerificationState.UNKNOWN:
            raise serializers.ValidationError("Start spot must be catalog-verified.")
        return value

    def validate_end_spot(self, value):
        if value.catalog_verification == WaterSpot.VerificationState.UNKNOWN:
            raise serializers.ValidationError("End spot must be catalog-verified.")
        return value

    def validate_plan_date(self, value):
        today = timezone.localdate()
        if value < today or value > today + timedelta(days=7):
            raise serializers.ValidationError(
                "Plan date must be today or within the next seven days."
            )
        return value

    def validate_title(self, value):
        return value.strip()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["start_minute"] >= attrs["end_minute"]:
            raise serializers.ValidationError(
                {"end_minute": "End minute must be later than start minute."}
            )
        return attrs


class SavedItinerarySerializer(serializers.ModelSerializer):
    start_spot_name = serializers.CharField(source="start_spot.name", read_only=True)
    end_spot_name = serializers.CharField(source="end_spot.name", read_only=True)
    evidence_status = serializers.SerializerMethodField()
    adult_supervision_confirmed = serializers.BooleanField(
        write_only=True,
        required=False,
    )

    class Meta:
        model = Itinerary
        fields = (
            "id",
            "title",
            "status",
            "activity",
            "participant_profile",
            "participant_skill_level",
            "plan_date",
            "start_spot",
            "start_spot_name",
            "end_spot",
            "end_spot_name",
            "start_minute",
            "end_minute",
            "transport",
            "is_day_trip",
            "party_size",
            "budget",
            "schedule",
            "policy_version",
            "route_snapshot_ids",
            "route_evidence",
            "water_evidence",
            "route_revalidation_required_at",
            "safety_revalidation_required_at",
            "execution_notice",
            "evidence_status",
            "adult_supervision_confirmed",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "activity",
            "participant_profile",
            "participant_skill_level",
            "plan_date",
            "start_spot",
            "start_spot_name",
            "end_spot",
            "end_spot_name",
            "start_minute",
            "end_minute",
            "transport",
            "is_day_trip",
            "party_size",
            "budget",
            "schedule",
            "policy_version",
            "route_snapshot_ids",
            "route_evidence",
            "water_evidence",
            "route_revalidation_required_at",
            "safety_revalidation_required_at",
            "execution_notice",
            "evidence_status",
            "created_at",
            "updated_at",
        )

    _TRANSITIONS = {
        Itinerary.Status.DRAFT: {
            Itinerary.Status.DRAFT,
            Itinerary.Status.ACCEPTED,
            Itinerary.Status.CANCELLED,
        },
        Itinerary.Status.ACCEPTED: {
            Itinerary.Status.ACCEPTED,
            Itinerary.Status.STARTED,
            Itinerary.Status.CANCELLED,
        },
        Itinerary.Status.STARTED: {
            Itinerary.Status.STARTED,
            Itinerary.Status.COMPLETED,
            Itinerary.Status.CANCELLED,
        },
        Itinerary.Status.COMPLETED: {Itinerary.Status.COMPLETED},
        Itinerary.Status.CANCELLED: {Itinerary.Status.CANCELLED},
    }

    def validate_title(self, value):
        return value.strip()

    def validate_status(self, value):
        if self.instance is None:
            return value
        allowed = self._TRANSITIONS[self.instance.status]
        if value not in allowed:
            raise serializers.ValidationError(
                f"Cannot transition itinerary from {self.instance.status} to {value}."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        supervision = attrs.pop("adult_supervision_confirmed", None)
        target_status = attrs.get("status")
        guarded_statuses = {Itinerary.Status.ACCEPTED, Itinerary.Status.STARTED}
        if supervision is not None and target_status not in guarded_statuses:
            raise serializers.ValidationError(
                {
                    "adult_supervision_confirmed": (
                        "Supervision can be confirmed only while accepting or "
                        "starting a family swimming itinerary."
                    )
                }
            )
        if self.instance is None or target_status not in guarded_statuses:
            return attrs

        supervision_required = (
            self.instance.requires_adult_supervision_reconfirmation()
        )
        if supervision is not None and not supervision_required:
            raise serializers.ValidationError(
                {
                    "adult_supervision_confirmed": (
                        "This itinerary does not require a supervision "
                        "reconfirmation."
                    )
                }
            )
        reasons = self.instance.evidence_revalidation_reasons(
            at=timezone.now(),
            adult_supervision_confirmed=supervision is True,
        )
        if reasons:
            raise serializers.ValidationError(
                {
                    "code": "ITINERARY_REVALIDATION_REQUIRED",
                    "reason_codes": list(reasons),
                    "detail": (
                        "Re-plan with current water and route evidence, or "
                        "reconfirm required session-only supervision before "
                        "accepting or starting this itinerary."
                    ),
                }
            )
        return attrs

    def get_evidence_status(self, obj):
        checked_at = timezone.now()
        reasons = obj.evidence_revalidation_reasons(at=checked_at)
        return {
            "state": "revalidation_required" if reasons else "current",
            "revalidation_required": bool(reasons),
            "reason_codes": list(reasons),
            "checked_at": checked_at,
        }
