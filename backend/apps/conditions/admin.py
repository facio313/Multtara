from django.contrib import admin

from .models import (
    ConditionScore,
    CrowdLevel,
    HydraulicCalibration,
    IngestionRun,
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
    PipelineHeartbeat,
    WaterCondition,
)


class ImmutableAuditAdmin(admin.ModelAdmin):
    """Expose persisted evidence for inspection without mutation paths."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ObservationMetricLineageInline(admin.TabularInline):
    model = ObservationMetricLineage
    fk_name = "derived_metric"
    extra = 0
    fields = ("source_metric", "relation", "priority", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ObservationMetric)
class ObservationMetricAdmin(ImmutableAuditAdmin):
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
class ObservationMetricLineageAdmin(ImmutableAuditAdmin):
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
class ObservationSnapshotAdmin(ImmutableAuditAdmin):
    list_display = ("id", "spot", "provider", "state", "observed_at", "fetched_at")
    list_filter = ("provider", "state")
    search_fields = ("spot__name", "provider_record_id")
    date_hierarchy = "fetched_at"
    inlines = (ObservationMetricInline,)


@admin.register(ConditionScore)
class ConditionScoreAdmin(ImmutableAuditAdmin):
    list_display = (
        "id",
        "spot",
        "activity",
        "participant_profile",
        "participant_skill_level",
        "score",
        "safety_status",
        "decision",
        "evaluated_at",
    )
    list_filter = (
        "activity",
        "participant_profile",
        "participant_skill_level",
        "safety_status",
        "decision",
        "methodology_version",
    )
    search_fields = ("spot__name",)
    date_hierarchy = "evaluated_at"


@admin.register(HydraulicCalibration)
class HydraulicCalibrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "spot",
        "version",
        "authority",
        "station_id",
        "verified",
        "active",
        "verified_at",
    )
    list_filter = ("authority", "verified", "active")
    search_fields = ("spot__name", "version", "station_id", "spatial_scope")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IngestionRun)
class IngestionRunAdmin(ImmutableAuditAdmin):
    list_display = ("task_name", "status", "started_at", "finished_at", "error_code")
    list_filter = ("task_name", "status", "started_at")
    search_fields = ("task_name", "error_code")
    readonly_fields = (
        "task_name",
        "status",
        "started_at",
        "finished_at",
        "error_code",
        "details",
    )


@admin.register(PipelineHeartbeat)
class PipelineHeartbeatAdmin(ImmutableAuditAdmin):
    list_display = ("key", "state", "last_seen_at")
    readonly_fields = ("key", "state", "current_tasks", "last_seen_at", "updated_at")

admin.site.register(WaterCondition)
admin.site.register(CrowdLevel)
