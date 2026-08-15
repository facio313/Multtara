from rest_framework import serializers

from apps.conditions.serializers import WaterConditionSerializer
from services.livecam import livecam_payload
from services.safety_radar import assess_safety, twin_facts
from services.tide_timer import summarize_tide
from .models import WaterSpot


class WaterSpotSerializer(serializers.ModelSerializer):
    scores = serializers.SerializerMethodField()
    water_index = serializers.SerializerMethodField()
    condition = serializers.SerializerMethodField()
    safety = serializers.SerializerMethodField()
    tide = serializers.SerializerMethodField()
    livecam = serializers.SerializerMethodField()
    crowd = serializers.SerializerMethodField()
    twin_facts = serializers.SerializerMethodField()

    class Meta:
        model = WaterSpot
        fields = (
            "id",
            "type",
            "name",
            "lat",
            "lng",
            "tourapi_id",
            "tags",
            "livecam_url",
            "pet_allowed",
            "accessibility",
            "region",
            "address",
            "image_url",
            "description",
            "khoa_obs_code",
            "kma_mid_reg_id",
            "scores",
            "water_index",
            "condition",
            "safety",
            "tide",
            "livecam",
            "crowd",
            "twin_facts",
        )

    def _activity(self) -> str:
        request = self.context.get("request")
        if request is None:
            return "swim"
        return request.query_params.get("activity", "swim")

    def get_scores(self, obj):
        latest = {}
        for row in obj.scores.all():
            if row.activity not in latest:
                latest[row.activity] = round(row.score)
        return latest

    def get_water_index(self, obj):
        annotated = getattr(obj, "annotated_index", None)
        if annotated is not None:
            return round(annotated)
        return self.get_scores(obj).get(self._activity())

    def _latest_related(self, obj, related_name: str):
        manager = getattr(obj, related_name)
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache is not None and related_name in cache:
            rows = manager.all()
        else:
            order = {"conditions": "-fetched_at", "crowd_levels": "-updated_at"}.get(related_name)
            rows = manager.order_by(order) if order else manager.all()
        return next(iter(rows), None)

    def get_condition(self, obj):
        latest = self._latest_related(obj, "conditions")
        if latest is None:
            return None
        return WaterConditionSerializer(latest).data

    def get_crowd(self, obj):
        latest = self._latest_related(obj, "crowd_levels")
        if latest is None:
            return None
        return {
            "predicted_level": latest.predicted_level,
            "recommended_time": latest.recommended_time,
            "parking_availability": latest.parking_availability,
        }

    def get_tide(self, obj):
        latest = self._latest_related(obj, "conditions")
        schedule = getattr(latest, "tide_schedule", None) if latest else {}
        return summarize_tide(schedule)

    def get_safety(self, obj):
        return assess_safety(
            obj.type,
            self._latest_related(obj, "conditions"),
            self._latest_related(obj, "crowd_levels"),
        )

    def get_twin_facts(self, obj):
        return twin_facts(
            obj.type,
            self._latest_related(obj, "conditions"),
            self._latest_related(obj, "crowd_levels"),
            self.get_tide(obj),
        )

    def get_livecam(self, obj):
        return livecam_payload(obj.livecam_url)
