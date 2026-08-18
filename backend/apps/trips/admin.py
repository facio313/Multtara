from django.contrib import admin

from .models import (
    Itinerary,
    RouteMatrixEntry,
    RouteMatrixSnapshot,
    SafetyCard,
)


@admin.register(Itinerary)
class ItineraryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "title",
        "activity",
        "plan_date",
        "transport",
        "status",
        "updated_at",
    )
    list_filter = ("status", "transport", "activity", "plan_date")
    search_fields = ("user__username", "title", "start_point")
    readonly_fields = (
        "status",
        "activity",
        "participant_profile",
        "participant_skill_level",
        "request_snapshot",
        "schedule",
        "policy_version",
        "route_snapshot_ids",
        "route_evidence",
        "water_evidence",
        "route_revalidation_required_at",
        "safety_revalidation_required_at",
        "execution_notice",
        "created_at",
        "updated_at",
    )


@admin.register(RouteMatrixSnapshot)
class RouteMatrixSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "transport",
        "state",
        "observed_at",
        "valid_until",
    )
    list_filter = ("provider", "transport", "state")
    readonly_fields = (
        "provider_record_id",
        "spot_set_hash",
        "observed_at",
        "fetched_at",
        "valid_until",
        "source_url",
        "created_at",
    )

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RouteMatrixEntry)
class RouteMatrixEntryAdmin(admin.ModelAdmin):
    list_display = (
        "snapshot",
        "origin_spot",
        "destination_spot",
        "duration_seconds",
        "distance_metres",
    )
    list_filter = ("snapshot__provider", "snapshot__transport")
    search_fields = ("origin_spot__name", "destination_spot__name")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(SafetyCard)
