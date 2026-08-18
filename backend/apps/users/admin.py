from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from django.utils import timezone

from .models import EcoAction, Passport, User, UserActivity


@admin.register(User)
class PongDangUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "PongDang profile",
            {"fields": ("persona_type", "mood_state", "home_region", "preferred_locale")},
        ),
    )


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "spot", "action", "rating", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username", "spot__name")


@admin.register(Passport)
class PassportAdmin(admin.ModelAdmin):
    list_display = ("user", "spot", "verification_method", "verified_at")
    list_filter = ("verification_method", "verified_at")
    search_fields = ("user__username", "spot__name", "verification_source")


@admin.register(EcoAction)
class EcoActionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "action_type",
        "spot",
        "state",
        "verified_by",
        "verified_at",
        "submitted_at",
    )
    list_filter = ("state", "action_type", "submitted_at")
    search_fields = ("user__username", "spot__name", "note")
    readonly_fields = ("submitted_at", "verified_at", "verified_by")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """Apply verification transitions under one row lock and transaction."""

        previous = None
        if change and obj.pk:
            previous = EcoAction.objects.select_for_update().filter(pk=obj.pk).first()
        if obj.state == EcoAction.VerificationState.VERIFIED:
            entering_verified = (
                previous is None
                or previous.state != EcoAction.VerificationState.VERIFIED
                or previous.verified_at is None
                or previous.verified_by_id is None
            )
            if entering_verified:
                obj.verified_at = timezone.now()
                obj.verified_by = request.user
            else:
                # Read-only audit fields survive unrelated edits by another
                # administrator; they are not silently re-attributed.
                obj.verified_at = previous.verified_at
                obj.verified_by_id = previous.verified_by_id
        else:
            obj.verified_at = None
            obj.verified_by = None
        obj.full_clean()
        super().save_model(request, obj, form, change)
