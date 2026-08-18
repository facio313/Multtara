import math

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class WaterForecast(models.Model):
    """Legacy, non-evidence-backed forecast row.

    Production access remains controlled by ``PUBLIC_LEGACY_WATER_FORECASTS``.
    New code must use :class:`DailyForecast` instead.
    """

    spot = models.ForeignKey("spots.WaterSpot", on_delete=models.CASCADE)
    forecast_date = models.DateField()
    predicted_index = models.FloatField()
    predicted_factors = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)


class GoldenMoment(models.Model):
    spot = models.ForeignKey("spots.WaterSpot", on_delete=models.CASCADE)
    date = models.DateField()
    time = models.TimeField()
    type = models.CharField(max_length=100)


class DailyForecast(models.Model):
    """One evidence-bound Water Index projection for an exact future instant.

    A date is not a promise that conditions hold for the whole day.  ``target_at``
    and the provider validity fields retain the exact instant/window evaluated.
    ``evidence`` is a credential-free copy of the selected raw metric provenance;
    a materially different provider record receives a different fingerprint.
    """

    class Activity(models.TextChoices):
        SWIM = "swim", "Swim"
        SURF = "surf", "Surf"
        RELAX = "relax", "Relax"
        MUDFLAT = "mudflat", "Mudflat"
        ONSEN = "onsen", "Onsen"
        RAFTING = "rafting", "Rafting"

    class ParticipantProfile(models.TextChoices):
        GENERAL = "general", "General"
        FAMILY = "family", "Family"

    class ParticipantSkillLevel(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    class SafetyStatus(models.TextChoices):
        CLEAR = "clear", "Clear"
        CAUTION = "caution", "Caution"
        STOP = "stop", "Stop"
        UNKNOWN = "unknown", "Unknown"

    class Decision(models.TextChoices):
        RECOMMENDED = "recommended", "Recommended"
        CONSIDER = "consider", "Consider"
        CAUTION = "caution", "Caution"
        NOT_RECOMMENDED = "not_recommended", "Not recommended"
        BLOCKED = "blocked", "Blocked"
        UNKNOWN = "unknown", "Unknown"

    class Availability(models.TextChoices):
        AVAILABLE = "available", "Available"
        PARTIAL = "partial", "Partial evidence"
        UNAVAILABLE = "unavailable", "Unavailable"

    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="daily_forecasts",
    )
    forecast_date = models.DateField()
    activity = models.CharField(max_length=20, choices=Activity.choices)
    participant_profile = models.CharField(
        max_length=16,
        choices=ParticipantProfile.choices,
        default=ParticipantProfile.GENERAL,
    )
    participant_skill_level = models.CharField(
        max_length=16,
        choices=ParticipantSkillLevel.choices,
        default=ParticipantSkillLevel.UNSPECIFIED,
    )
    target_at = models.DateTimeField()
    score = models.FloatField(null=True, blank=True)
    safety_status = models.CharField(
        max_length=12,
        choices=SafetyStatus.choices,
        default=SafetyStatus.UNKNOWN,
    )
    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
        default=Decision.UNKNOWN,
    )
    confidence = models.FloatField(default=0.0)
    coverage = models.FloatField(default=0.0)
    score_range = models.JSONField(default=list, blank=True)
    gates = models.JSONField(default=list, blank=True)
    contributions = models.JSONField(default=list, blank=True)
    missing_metrics = models.JSONField(default=list, blank=True)
    stale_or_conflicting_metrics = models.JSONField(default=list, blank=True)
    limitations = models.JSONField(default=list, blank=True)
    availability = models.CharField(
        max_length=16,
        choices=Availability.choices,
        default=Availability.UNAVAILABLE,
    )
    unavailable_reason = models.CharField(max_length=100, blank=True)
    evidence = models.JSONField(default=list, blank=True)
    evidence_fingerprint = models.CharField(max_length=64)
    evidence_issued_at = models.DateTimeField(null=True, blank=True)
    evidence_fetched_at = models.DateTimeField(null=True, blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    methodology_version = models.CharField(max_length=100)
    projection_methodology_version = models.CharField(max_length=100)
    evaluated_at = models.DateTimeField()
    computed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("forecast_date", "-evaluated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "spot",
                    "forecast_date",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "methodology_version",
                    "projection_methodology_version",
                    "evidence_fingerprint",
                ),
                name="daily_fcst_evidence_uniq",
            ),
            models.CheckConstraint(
                condition=Q(score__isnull=True)
                | (Q(score__gte=0.0) & Q(score__lte=100.0)),
                name="daily_fcst_score_range",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0.0) & Q(confidence__lte=1.0),
                name="daily_fcst_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(coverage__gte=0.0) & Q(coverage__lte=1.0),
                name="daily_fcst_coverage_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    activity__in=(
                        "swim",
                        "surf",
                        "relax",
                        "mudflat",
                        "onsen",
                        "rafting",
                    )
                ),
                name="daily_fcst_activity_valid",
            ),
            models.CheckConstraint(
                condition=Q(participant_profile__in=("general", "family")),
                name="daily_fcst_profile_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        activity="surf",
                        participant_skill_level__in=(
                            "unspecified",
                            "beginner",
                            "intermediate",
                            "advanced",
                        ),
                    )
                    | (
                        ~Q(activity="surf")
                        & Q(participant_skill_level="unspecified")
                    )
                ),
                name="daily_fcst_skill_activity_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(
                        activity="surf",
                        participant_skill_level="unspecified",
                    )
                    | (
                        Q(score__isnull=True)
                        & (
                            Q(safety_status="clear", decision="unknown")
                            | Q(safety_status="unknown", decision="unknown")
                            | Q(safety_status="caution", decision="caution")
                            | Q(safety_status="stop", decision="blocked")
                        )
                    )
                ),
                name="daily_fcst_surf_unscoped_policy",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_until__gte=models.F("valid_from")),
                name="daily_fcst_valid_window",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        safety_status="clear",
                        decision__in=(
                            "recommended",
                            "consider",
                            "not_recommended",
                        ),
                        score__isnull=False,
                    )
                    | Q(
                        safety_status="clear",
                        decision="unknown",
                        score__isnull=True,
                    )
                    | Q(
                        safety_status="caution",
                        decision="caution",
                    )
                    & (Q(score__isnull=True) | Q(score__lte=39.0))
                    | Q(
                        safety_status="stop",
                        decision="blocked",
                        score__isnull=True,
                    )
                    | Q(
                        safety_status="unknown",
                        decision="unknown",
                        score__isnull=True,
                    )
                ),
                name="daily_fcst_public_policy",
            ),
            models.CheckConstraint(
                condition=(
                    Q(availability="available", unavailable_reason="")
                    | Q(
                        availability__in=("partial", "unavailable"),
                    )
                    & ~Q(unavailable_reason="")
                ),
                name="daily_fcst_reason_policy",
            ),
            models.CheckConstraint(
                condition=(
                    Q(availability="available")
                    | Q(
                        availability__in=("partial", "unavailable"),
                        safety_status="unknown",
                        decision="unknown",
                        score__isnull=True,
                        score_range=[],
                        contributions=[],
                    )
                ),
                name="daily_fcst_availability_public",
            ),
            models.CheckConstraint(
                condition=Q(score__isnull=False) | Q(score_range=[]),
                name="daily_fcst_null_range_empty",
            ),
            models.CheckConstraint(
                condition=~Q(evidence_fingerprint=""),
                name="daily_fcst_fingerprint_required",
            ),
            models.CheckConstraint(
                condition=Q(evidence_issued_at__isnull=True)
                | Q(evidence_fetched_at__isnull=True)
                | Q(evidence_issued_at__lte=models.F("evidence_fetched_at")),
                name="daily_fcst_issue_before_fetch",
            ),
        ]
        indexes = [
            models.Index(
                fields=(
                    "spot",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "forecast_date",
                    "-evaluated_at",
                ),
                name="daily_fcst_lookup_idx",
            ),
            models.Index(
                fields=("availability", "forecast_date"),
                name="daily_fcst_avail_date_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.target_at and self.forecast_date:
            if self.target_at.date() != self.forecast_date:
                errors["target_at"] = "target_at must fall on forecast_date."
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors["valid_until"] = "valid_until cannot be earlier than valid_from."
        if not isinstance(self.evidence, list):
            errors["evidence"] = "evidence must be a list."
        if self.availability == self.Availability.AVAILABLE:
            if self.unavailable_reason:
                errors["unavailable_reason"] = (
                    "available forecasts cannot have an unavailable reason."
                )
        elif not self.unavailable_reason:
            errors["unavailable_reason"] = (
                "partial and unavailable forecasts require an explicit reason."
            )
        if self.availability != self.Availability.AVAILABLE and (
            self.safety_status != self.SafetyStatus.UNKNOWN
            or self.decision != self.Decision.UNKNOWN
            or self.score is not None
            or bool(self.score_range)
            or bool(self.contributions)
        ):
            errors["availability"] = (
                "Partial and unavailable forecasts cannot publish a safety "
                "state, suitability score, score range, or contributions."
            )
        if self.score is None:
            if self.score_range:
                errors["score_range"] = (
                    "A forecast without a score must have an empty score range."
                )
        else:
            valid_range = (
                isinstance(self.score_range, list)
                and len(self.score_range) == 2
                and all(
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(float(value))
                    for value in self.score_range
                )
            )
            if valid_range:
                lower, upper = (float(value) for value in self.score_range)
                valid_range = (
                    0.0 <= lower <= float(self.score) <= upper <= 100.0
                )
            if not valid_range:
                errors["score_range"] = (
                    "A scored forecast requires [lower, upper] within 0..100 "
                    "and containing the score."
                )
        if self.activity == self.Activity.SURF:
            if (
                self.participant_skill_level
                == self.ParticipantSkillLevel.UNSPECIFIED
            ):
                valid_unscoped_state = self.score is None and (
                    (
                        self.safety_status
                        in {self.SafetyStatus.CLEAR, self.SafetyStatus.UNKNOWN}
                        and self.decision == self.Decision.UNKNOWN
                    )
                    or (
                        self.safety_status == self.SafetyStatus.CAUTION
                        and self.decision == self.Decision.CAUTION
                    )
                    or (
                        self.safety_status == self.SafetyStatus.STOP
                        and self.decision == self.Decision.BLOCKED
                    )
                )
                if not valid_unscoped_state:
                    errors["participant_skill_level"] = (
                        "An unscoped surf forecast cannot publish a participant "
                        "suitability score or decision."
                    )
                if self.score_range:
                    errors["score_range"] = (
                        "An unscoped surf forecast cannot publish a score range."
                    )
        elif (
            self.participant_skill_level
            != self.ParticipantSkillLevel.UNSPECIFIED
        ):
            errors["participant_skill_level"] = (
                "Non-surf forecasts must use the unspecified skill identity."
            )
        if errors:
            raise ValidationError(errors)
