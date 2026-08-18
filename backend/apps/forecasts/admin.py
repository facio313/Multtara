from django.contrib import admin

from .models import DailyForecast, GoldenMoment, WaterForecast

admin.site.register(WaterForecast)
admin.site.register(GoldenMoment)


@admin.register(DailyForecast)
class DailyForecastAdmin(admin.ModelAdmin):
    list_display = (
        "spot",
        "forecast_date",
        "activity",
        "participant_profile",
        "participant_skill_level",
        "safety_status",
        "availability",
        "evaluated_at",
    )
    list_filter = (
        "activity",
        "participant_profile",
        "participant_skill_level",
        "safety_status",
        "availability",
        "forecast_date",
    )
    search_fields = ("spot__name", "unavailable_reason")
    readonly_fields = (
        "score",
        "safety_status",
        "decision",
        "confidence",
        "coverage",
        "score_range",
        "gates",
        "contributions",
        "missing_metrics",
        "stale_or_conflicting_metrics",
        "limitations",
        "availability",
        "unavailable_reason",
        "evidence",
        "evidence_fingerprint",
        "evidence_issued_at",
        "evidence_fetched_at",
        "valid_from",
        "valid_until",
        "methodology_version",
        "projection_methodology_version",
        "evaluated_at",
        "computed_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
