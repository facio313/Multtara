from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from services.public_urls import public_https_url


class User(AbstractUser):
    class Locale(models.TextChoices):
        KOREAN = "ko", "Korean"
        ENGLISH = "en", "English"
        JAPANESE = "ja", "Japanese"
        CHINESE_SIMPLIFIED = "zh-hans", "Chinese (Simplified)"

    persona_type = models.CharField(max_length=50, blank=True)
    mood_state = models.CharField(max_length=50, blank=True)
    home_region = models.CharField(max_length=100, blank=True)
    preferred_locale = models.CharField(
        max_length=12,
        choices=Locale.choices,
        default=Locale.KOREAN,
    )
    # The identity provider subject is the durable account key.  Email and
    # display names may be reused or changed, so neither is safe as the ongoing
    # session binding.  ``NULL`` preserves local-development and legacy users;
    # once linked, the model deliberately refuses replacement or removal.
    sso_subject = models.CharField(
        max_length=254,
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            previous_subject = (
                type(self)
                ._base_manager.filter(pk=self.pk)
                .values_list("sso_subject", flat=True)
                .first()
            )
            if previous_subject is not None and previous_subject != self.sso_subject:
                raise ValidationError(
                    {"sso_subject": "A linked SSO subject is immutable."}
                )
        return super().save(*args, **kwargs)


class UserActivity(models.Model):
    """A small first-party interaction record, never a safety observation."""

    class Action(models.TextChoices):
        CLICK = "click", "Click"
        SAVE = "save", "Save"
        UNSAVE = "unsave", "Unsave"
        DISMISS = "dismiss", "Dismiss"
        VISIT = "visit", "Visit"
        REVIEW = "review", "Review"
        REPORT = "report", "Report"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="spot_activities",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="user_activities",
    )
    # Keep the historical 50-character storage width so old operator-defined
    # action labels are not truncated during migration. New API writes remain
    # restricted to the explicit choices above.
    action = models.CharField(max_length=50, choices=Action.choices)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1), MaxValueValidator(5)),
    )
    review_text = models.TextField(blank=True, max_length=2_000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5),
                name="user_activity_rating_range",
            ),
            models.CheckConstraint(
                condition=Q(action="review")
                | (Q(rating__isnull=True) & Q(review_text="")),
                name="user_activity_review_fields_only",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "action", "-created_at"),
                name="user_activity_action_idx",
            ),
        ]


class Passport(models.Model):
    """Operator-verified visit; clients cannot mint these records themselves."""

    class VerificationMethod(models.TextChoices):
        OPERATOR = "operator", "Operator"
        QR = "qr", "On-site QR"
        PARTNER = "partner", "Verified partner"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="passports",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="passports",
    )
    verified_at = models.DateTimeField(auto_now_add=True)
    verification_method = models.CharField(
        max_length=16,
        choices=VerificationMethod.choices,
        default=VerificationMethod.OPERATOR,
    )
    verification_source = models.CharField(max_length=100, blank=True)
    evidence_url = models.URLField(max_length=500, blank=True)
    badge_earned = models.JSONField(default=dict, blank=True)
    # Legacy display field. New eco claims use EcoAction so an unverified
    # self-report cannot silently become an earned badge.
    eco_action = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-verified_at", "-id")

    def clean(self) -> None:
        super().clean()
        if not self.evidence_url:
            return
        sanitized = public_https_url(self.evidence_url)
        if not sanitized:
            raise ValidationError(
                {"evidence_url": "Evidence URL must be a public HTTPS URL."}
            )
        self.evidence_url = sanitized

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class EcoAction(models.Model):
    """User-submitted eco action with an explicit verification lifecycle."""

    class ActionType(models.TextChoices):
        CLEANUP = "cleanup", "Cleanup"
        REUSABLE = "reusable", "Reusable container"
        LOCAL = "local", "Local business"
        TRANSIT = "transit", "Low-carbon transport"
        SAFETY_SHARE = "safety_share", "Safety information sharing"

    class VerificationState(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eco_actions",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eco_actions",
    )
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    note = models.CharField(max_length=500, blank=True)
    evidence_url = models.URLField(max_length=500, blank=True)
    occurred_on = models.DateField()
    state = models.CharField(
        max_length=12,
        choices=VerificationState.choices,
        default=VerificationState.PENDING,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # A verification must retain its accountable operator. SET_NULL would
        # violate the state invariant during a verifier deletion.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="verified_eco_actions",
    )

    class Meta:
        ordering = ("-submitted_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    state="verified",
                    verified_at__isnull=False,
                    verified_by__isnull=False,
                )
                | (
                    ~Q(state="verified")
                    & Q(verified_at__isnull=True, verified_by__isnull=True)
                ),
                name="eco_verification_fields_match_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.evidence_url:
            sanitized = public_https_url(self.evidence_url)
            if not sanitized:
                errors["evidence_url"] = "Evidence URL must be a public HTTPS URL."
            else:
                # Never retain URL credentials, query tokens, or fragments.
                self.evidence_url = sanitized
        if self.state == self.VerificationState.VERIFIED:
            if self.verified_at is None:
                errors["verified_at"] = (
                    "A verified eco action requires a verification time."
                )
            if self.verified_by_id is None:
                errors["verified_by"] = (
                    "A verified eco action requires a verifying operator."
                )
        else:
            if self.verified_at is not None:
                errors["verified_at"] = (
                    "A non-verified eco action cannot retain a verification time."
                )
            if self.verified_by_id is not None:
                errors["verified_by"] = (
                    "A non-verified eco action cannot retain a verifying operator."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
