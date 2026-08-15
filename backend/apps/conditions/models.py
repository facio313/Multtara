from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class WaterCondition(models.Model):
    """Legacy denormalized condition row kept for API and fixture compatibility."""

    spot = models.ForeignKey("spots.WaterSpot", on_delete=models.CASCADE)
    water_temp = models.FloatField(null=True, blank=True)
    air_temp = models.FloatField(null=True, blank=True)
    wind_speed = models.FloatField(null=True, blank=True)
    wave_height = models.FloatField(null=True, blank=True)
    water_quality_grade = models.CharField(max_length=50, blank=True)
    rainfall_recent = models.FloatField(null=True, blank=True)
    water_level = models.FloatField(null=True, blank=True)
    tide_schedule = models.JSONField(default=dict, blank=True)
    rip_current_risk = models.CharField(max_length=50, blank=True)
    uv_index = models.FloatField(null=True, blank=True)
    weather_alert = models.CharField(max_length=200, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)


class ObservationSnapshot(models.Model):
    """One provider response normalized into auditable scalar observations.

    Raw provider payloads and request credentials intentionally do not belong in
    this model. A snapshot records only the public provenance needed to audit
    its normalized metrics.
    """

    class SourceState(models.TextChoices):
        LIVE = "live", "Live"
        DEMO = "demo", "Demo"
        MISSING = "missing", "Missing"
        STALE = "stale", "Stale"
        ERROR = "error", "Error"

    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="observation_snapshots",
    )
    provider = models.CharField(max_length=100)
    provider_record_id = models.CharField(max_length=200, blank=True)
    state = models.CharField(
        max_length=16,
        choices=SourceState.choices,
        default=SourceState.LIVE,
    )
    observed_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    spatial_scope = models.CharField(max_length=200)
    source_url = models.URLField(max_length=500, blank=True)
    ingestion_version = models.CharField(max_length=100, default="unversioned")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fetched_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("spot", "provider", "provider_record_id", "ingestion_version"),
                condition=~Q(provider_record_id=""),
                name="condition_snapshot_provider_record_uniq",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_until__gte=F("valid_from")),
                name="condition_snapshot_valid_window",
            ),
            models.CheckConstraint(
                condition=Q(observed_at__isnull=True) | Q(observed_at__lte=F("fetched_at")),
                name="condition_snapshot_observed_before_fetch",
            ),
            models.CheckConstraint(
                condition=Q(state__in=("live", "demo", "missing", "stale", "error")),
                name="condition_snapshot_state_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("spot", "-fetched_at"), name="cond_snap_spot_fetch_idx"),
            models.Index(
                fields=("provider", "provider_record_id"),
                name="cond_snap_provider_rec_idx",
            ),
            models.Index(fields=("state", "-fetched_at"), name="cond_snap_state_fetch_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.observed_at and self.fetched_at and self.observed_at > self.fetched_at:
            errors["observed_at"] = "observed_at cannot be later than fetched_at."
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors["valid_until"] = "valid_until cannot be earlier than valid_from."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.provider}:{self.spot_id}@{self.fetched_at.isoformat()}"


class ObservationMetric(models.Model):
    """A typed scalar observation with explicit time and source provenance."""

    class ValueType(models.TextChoices):
        NUMBER = "number", "Number"
        TEXT = "text", "Text"
        BOOLEAN = "boolean", "Boolean"

    class Mode(models.TextChoices):
        OBSERVED = "observed", "Observed"
        FORECAST = "forecast", "Forecast"
        ESTIMATED = "estimated", "Estimated"
        USER_REPORTED = "user_reported", "User reported"

    class State(models.TextChoices):
        VALID = "valid", "Valid"
        CONFLICT = "conflict", "Conflict"
        INVALID = "invalid", "Invalid"
        MISSING = "missing", "Missing"
        STALE = "stale", "Stale"

    snapshot = models.ForeignKey(
        ObservationSnapshot,
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    name = models.CharField(max_length=100)
    value_type = models.CharField(max_length=12, choices=ValueType.choices)
    numeric_value = models.FloatField(null=True, blank=True)
    text_value = models.TextField(null=True, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.OBSERVED)
    state = models.CharField(max_length=12, choices=State.choices, default=State.VALID)
    confidence = models.FloatField(default=1.0)
    source = models.CharField(max_length=100)
    source_url = models.URLField(max_length=500, blank=True)
    station_id = models.CharField(max_length=100, blank=True)
    spatial_scope = models.CharField(max_length=200)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("snapshot", "name"),
                name="condition_metric_snapshot_name_uniq",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0.0) & Q(confidence__lte=1.0),
                name="condition_metric_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(observed_at__lte=F("fetched_at")),
                name="condition_metric_observed_before_fetch",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_until__gte=F("valid_from")),
                name="condition_metric_valid_window",
            ),
            models.CheckConstraint(
                condition=Q(value_type__in=("number", "text", "boolean")),
                name="condition_metric_value_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(mode__in=("observed", "forecast", "estimated", "user_reported")),
                name="condition_metric_mode_valid",
            ),
            models.CheckConstraint(
                condition=~Q(mode="forecast")
                | (Q(valid_from__isnull=False) & Q(valid_until__isnull=False)),
                name="condition_metric_forecast_window",
            ),
            models.CheckConstraint(
                condition=Q(state__in=("valid", "conflict", "invalid", "missing", "stale")),
                name="condition_metric_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state="missing",
                        numeric_value__isnull=True,
                        text_value__isnull=True,
                        boolean_value__isnull=True,
                    )
                    | Q(
                        ~Q(state="missing"),
                        value_type="number",
                        numeric_value__isnull=False,
                        text_value__isnull=True,
                        boolean_value__isnull=True,
                    )
                    | Q(
                        ~Q(state="missing"),
                        value_type="text",
                        numeric_value__isnull=True,
                        text_value__isnull=False,
                        boolean_value__isnull=True,
                    )
                    | Q(
                        ~Q(state="missing"),
                        value_type="boolean",
                        numeric_value__isnull=True,
                        text_value__isnull=True,
                        boolean_value__isnull=False,
                    )
                ),
                name="condition_metric_typed_value",
            ),
        ]
        indexes = [
            models.Index(fields=("snapshot", "name"), name="cond_metric_snap_name_idx"),
            models.Index(fields=("source", "name"), name="cond_metric_source_name_idx"),
            models.Index(fields=("state", "-fetched_at"), name="cond_metric_state_fetch_idx"),
        ]

    @property
    def value(self) -> float | str | bool | None:
        if self.state == self.State.MISSING:
            return None
        return {
            self.ValueType.NUMBER: self.numeric_value,
            self.ValueType.TEXT: self.text_value,
            self.ValueType.BOOLEAN: self.boolean_value,
        }.get(self.value_type)

    def clean(self) -> None:
        super().clean()
        values = {
            self.ValueType.NUMBER: self.numeric_value,
            self.ValueType.TEXT: self.text_value,
            self.ValueType.BOOLEAN: self.boolean_value,
        }
        populated = [kind for kind, value in values.items() if value is not None]
        if self.state == self.State.MISSING:
            if populated:
                raise ValidationError("A missing metric cannot store a value.")
        elif populated != [self.value_type]:
            raise ValidationError(
                "Exactly one value column matching value_type must be populated."
            )
        errors: dict[str, str] = {}
        if self.observed_at and self.fetched_at and self.observed_at > self.fetched_at:
            errors["observed_at"] = "observed_at cannot be later than fetched_at."
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors["valid_until"] = "valid_until cannot be earlier than valid_from."
        if self.mode == self.Mode.FORECAST and (
            self.valid_from is None or self.valid_until is None
        ):
            errors["valid_from"] = (
                "Forecast metrics require both valid_from and valid_until."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.snapshot_id}:{self.name}"


class ObservationMetricLineage(models.Model):
    """An explicit edge from one fused metric to an original provider metric."""

    class Relation(models.TextChoices):
        SELECTED = "selected", "Selected input"
        CONFLICT = "conflict", "Conflicting input"

    derived_metric = models.ForeignKey(
        ObservationMetric,
        on_delete=models.CASCADE,
        related_name="lineage_sources",
    )
    source_metric = models.ForeignKey(
        ObservationMetric,
        on_delete=models.RESTRICT,
        related_name="lineage_derivations",
    )
    relation = models.CharField(max_length=16, choices=Relation.choices)
    priority = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("derived_metric_id", "-priority", "source_metric_id")
        constraints = [
            models.UniqueConstraint(
                fields=("derived_metric", "source_metric"),
                name="cond_metric_lineage_edge_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(derived_metric=F("source_metric")),
                name="cond_metric_lineage_not_self",
            ),
            models.CheckConstraint(
                condition=Q(relation__in=("selected", "conflict")),
                name="cond_metric_lineage_relation_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("derived_metric", "relation"),
                name="cond_lineage_derived_rel_idx",
            ),
            models.Index(
                fields=("source_metric",),
                name="cond_lineage_source_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.derived_metric_id == self.source_metric_id:
            errors["source_metric"] = "A metric cannot derive from itself."
        if self.derived_metric_id and self.source_metric_id:
            derived_snapshot = self.derived_metric.snapshot
            source_snapshot = self.source_metric.snapshot
            if derived_snapshot.provider != "PONGDANG_FUSION":
                errors["derived_metric"] = (
                    "Lineage can only be attached to a fused metric."
                )
            if source_snapshot.provider == "PONGDANG_FUSION":
                errors["source_metric"] = (
                    "A lineage source must be an original provider metric."
                )
            if derived_snapshot.spot_id != source_snapshot.spot_id:
                errors["source_metric"] = (
                    "Derived and source metrics must belong to the same spot."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.derived_metric_id}<-{self.source_metric_id}:"
            f"{self.relation}@{self.priority}"
        )


class ConditionScore(models.Model):
    class ParticipantProfile(models.TextChoices):
        UNKNOWN = "unknown", "Unknown legacy profile"
        GENERAL = "general", "General"
        FAMILY = "family", "Family"

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

    spot = models.ForeignKey("spots.WaterSpot", on_delete=models.CASCADE)
    snapshot = models.ForeignKey(
        ObservationSnapshot,
        on_delete=models.SET_NULL,
        related_name="condition_scores",
        null=True,
        blank=True,
    )
    activity = models.CharField(max_length=100)
    participant_profile = models.CharField(
        max_length=16,
        choices=ParticipantProfile.choices,
        default=ParticipantProfile.GENERAL,
    )
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
    methodology_version = models.CharField(max_length=100, default="legacy-unversioned")
    evaluated_at = models.DateTimeField(default=timezone.now)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-evaluated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "snapshot",
                    "activity",
                    "participant_profile",
                    "methodology_version",
                ),
                condition=Q(snapshot__isnull=False),
                name="cond_score_snap_act_prof_uniq",
            ),
            models.CheckConstraint(
                condition=Q(score__isnull=True) | (Q(score__gte=0.0) & Q(score__lte=100.0)),
                name="condition_score_range",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0.0) & Q(confidence__lte=1.0),
                name="condition_score_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(coverage__gte=0.0) & Q(coverage__lte=1.0),
                name="condition_score_coverage_range",
            ),
            models.CheckConstraint(
                condition=Q(safety_status__in=("clear", "caution", "stop", "unknown")),
                name="condition_score_safety_valid",
            ),
            models.CheckConstraint(
                condition=Q(participant_profile__in=("unknown", "general", "family")),
                name="cond_score_profile_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    decision__in=(
                        "recommended",
                        "consider",
                        "caution",
                        "not_recommended",
                        "blocked",
                        "unknown",
                    )
                ),
                name="condition_score_decision_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(methodology_version="legacy-unversioned")
                    | Q(
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
                name="condition_score_public_policy",
            ),
        ]
        indexes = [
            models.Index(
                fields=("spot", "activity", "participant_profile", "-evaluated_at"),
                name="cond_score_spot_act_prof_idx",
            ),
            models.Index(
                fields=("safety_status", "decision", "-evaluated_at"),
                name="cond_score_safety_dec_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.snapshot_id and self.spot_id and self.snapshot.spot_id != self.spot_id:
            errors["snapshot"] = "snapshot and score must belong to the same spot."
        if self.score_range:
            if not isinstance(self.score_range, (list, tuple)) or len(self.score_range) != 2:
                errors["score_range"] = "score_range must contain [lower, upper]."
            else:
                lower, upper = self.score_range
                if (
                    isinstance(lower, bool)
                    or isinstance(upper, bool)
                    or not isinstance(lower, (int, float))
                    or not isinstance(upper, (int, float))
                    or not 0 <= lower <= upper <= 100
                ):
                    errors["score_range"] = (
                        "score_range bounds must satisfy 0 <= lower <= upper <= 100."
                    )
                elif self.score is not None and not lower <= self.score <= upper:
                    errors["score_range"] = "score must fall inside score_range."
        if self.methodology_version != "legacy-unversioned":
            valid_public_state = (
                self.safety_status == self.SafetyStatus.CLEAR
                and (
                    (
                        self.decision
                        in {
                            self.Decision.RECOMMENDED,
                            self.Decision.CONSIDER,
                            self.Decision.NOT_RECOMMENDED,
                        }
                        and self.score is not None
                    )
                    or (
                        self.decision == self.Decision.UNKNOWN
                        and self.score is None
                    )
                )
            ) or (
                self.safety_status == self.SafetyStatus.CAUTION
                and self.decision == self.Decision.CAUTION
                and (self.score is None or self.score <= 39)
            ) or (
                self.safety_status == self.SafetyStatus.STOP
                and self.decision == self.Decision.BLOCKED
                and self.score is None
            ) or (
                self.safety_status == self.SafetyStatus.UNKNOWN
                and self.decision == self.Decision.UNKNOWN
                and self.score is None
            )
            if not valid_public_state:
                errors["safety_status"] = (
                    "Safety status, decision, and public score violate the "
                    "fail-closed Water Index contract."
                )
        for field_name in (
            "gates",
            "contributions",
            "missing_metrics",
            "stale_or_conflicting_metrics",
            "limitations",
        ):
            if not isinstance(getattr(self, field_name), list):
                errors[field_name] = f"{field_name} must be a list."
        if errors:
            raise ValidationError(errors)


class CrowdLevel(models.Model):
    spot = models.ForeignKey("spots.WaterSpot", on_delete=models.CASCADE)
    predicted_level = models.CharField(max_length=50)
    recommended_time = models.CharField(max_length=100, blank=True)
    parking_availability = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
