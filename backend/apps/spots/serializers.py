from rest_framework import serializers

from apps.conditions.serializers import ConditionScoreSerializer, WaterConditionSerializer
from apps.forecasts.serializers import WaterForecastSerializer
from .models import WaterSpot


class WaterSpotSerializer(serializers.ModelSerializer):
    scores = serializers.SerializerMethodField()
    water_index = serializers.SerializerMethodField()
    condition = serializers.SerializerMethodField()

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

    def get_condition(self, obj):
        conditions = (
            obj.conditions.all()
            if hasattr(obj, "_prefetched_objects_cache")
            else obj.conditions.order_by("-fetched_at")
        )
        latest = next(iter(conditions), None)
        if latest is None:
            return None
        return WaterConditionSerializer(latest).data
