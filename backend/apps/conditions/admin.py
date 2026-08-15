from django.contrib import admin

from .models import (
    ConditionScore,
    CrowdLevel,
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
    WaterCondition,
)


class ObservationMetricInline(admin.TabularInline):
    model = ObservationMetric
    extra = 0
    fields = (
        "name",
        "value_type",
        "numeric_value",
        "text_value",
        "boolean_value",
        "unit",
        "state",
        "confidence",
        "source",
        "observed_at",
    )
    readonly_fields = fields


class ObservationMetricLineageInline(admin.TabularInline):
    model = ObservationMetricLineage
    fk_name = "derived_metric"
    extra = 0
    fields = ("source_metric", "relation", "priority", "created_at")
    readonly_fields = fields


@admin.register(ObservationMetric)
class ObservationMetricAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snapshot",
        "name",
        "source",
        "state",
        "observed_at",
    )
    list_filter = ("source", "state", "mode")
    search_fields = ("name", "snapshot__spot__name", "snapshot__provider_record_id")
    inlines = (ObservationMetricLineageInline,)


@admin.register(ObservationMetricLineage)
class ObservationMetricLineageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "derived_metric",
        "source_metric",
        "relation",
        "priority",
    )
    list_filter = ("relation",)
    search_fields = (
        "derived_metric__name",
        "source_metric__name",
        "source_metric__snapshot__provider_record_id",
    )


@admin.register(ObservationSnapshot)
class ObservationSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "spot", "provider", "state", "observed_at", "fetched_at")
    list_filter = ("provider", "state")
    search_fields = ("spot__name", "provider_record_id")
    date_hierarchy = "fetched_at"
    inlines = (ObservationMetricInline,)


@admin.register(ConditionScore)
class ConditionScoreAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "spot",
        "activity",
        "participant_profile",
        "score",
        "safety_status",
        "decision",
        "evaluated_at",
    )
    list_filter = (
        "activity",
        "participant_profile",
        "safety_status",
        "decision",
        "methodology_version",
    )
    search_fields = ("spot__name",)
    date_hierarchy = "evaluated_at"

admin.site.register(WaterCondition)
admin.site.register(CrowdLevel)
