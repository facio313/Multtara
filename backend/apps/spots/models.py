from __future__ import annotations

import math

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class WaterSpot(models.Model):
    class SpotType(models.TextChoices):
        BEACH = "beach", "Beach"
        RIVER = "river", "River"
        VALLEY = "valley", "Valley"
        HOTSPRING = "hotspring", "Hot spring"
        POOL = "pool", "Pool"
        WATERPARK = "waterpark", "Water park"
        LAKE = "lake", "Lake"
        WATERFALL = "waterfall", "Waterfall"
        RIVERSIDE = "riverside", "Riverside"
        RESERVOIR = "reservoir", "Reservoir"
        MUDFLAT = "mudflat", "Mudflat"
        COASTAL_ROAD = "coastal_road", "Coastal road"

    class VerificationState(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        PARTIAL = "partial", "Partially verified"
        VERIFIED = "verified", "Verified"

    class AccessibilityState(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        PARTIAL = "partial", "Partially verified"
        VERIFIED = "verified", "Verified"
        UNAVAILABLE = "unavailable", "Unavailable"

    class PolicyState(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        ALLOWED = "allowed", "Allowed"
        NOT_ALLOWED = "not_allowed", "Not allowed"
        CONDITIONAL = "conditional", "Conditional"

    SPOT_TYPES = SpotType.choices

    type = models.CharField(max_length=24, choices=SpotType.choices)
    name = models.CharField(max_length=200)
    lat = models.FloatField(
        validators=(MinValueValidator(-90.0), MaxValueValidator(90.0))
    )
    lng = models.FloatField(
        validators=(MinValueValidator(-180.0), MaxValueValidator(180.0))
    )
    tourapi_id = models.CharField(max_length=100, blank=True)
    khoa_beach_code = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    livecam_url = models.URLField(blank=True)
    # Legacy boolean retained for migration/API compatibility. New decision
    # code must use pet_policy because False cannot distinguish no from unknown.
    pet_allowed = models.BooleanField(default=False)
    pet_policy = models.CharField(
        max_length=16,
        choices=PolicyState.choices,
        default=PolicyState.UNKNOWN,
    )
    accessibility = models.CharField(max_length=200, blank=True)
    accessibility_state = models.CharField(
        max_length=16,
        choices=AccessibilityState.choices,
        default=AccessibilityState.UNKNOWN,
    )
    region = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    image_url = models.URLField(blank=True)
    description = models.TextField(blank=True)

    # Structured catalog evidence consumed by the recommendation boundary.
    preference_features = models.JSONField(default=dict, blank=True)
    opening_windows = models.JSONField(default=list, blank=True)
    typical_duration_minutes = models.PositiveIntegerField(default=60)
    cost_krw = models.PositiveIntegerField(null=True, blank=True)
    age_policy_known = models.BooleanField(default=False)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    maximum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    indoor = models.BooleanField(default=False)
    bad_weather_suitable = models.BooleanField(default=False)
    catalog_confidence = models.FloatField(
        default=0.0,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )
    catalog_verification = models.CharField(
        max_length=16,
        choices=VerificationState.choices,
        default=VerificationState.UNKNOWN,
    )
    catalog_source = models.CharField(max_length=100, blank=True)
    catalog_source_url = models.URLField(max_length=500, blank=True)
    catalog_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("region", "name", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(lat__gte=-90.0) & Q(lat__lte=90.0),
                name="spot_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(lng__gte=-180.0) & Q(lng__lte=180.0),
                name="spot_longitude_range",
            ),
            models.CheckConstraint(
                condition=Q(catalog_confidence__gte=0.0)
                & Q(catalog_confidence__lte=1.0),
                name="spot_catalog_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(maximum_age__isnull=True)
                | Q(minimum_age__isnull=True)
                | Q(maximum_age__gte=F("minimum_age")),
                name="spot_age_policy_range",
            ),
            models.CheckConstraint(
                condition=Q(age_policy_known=False) | Q(minimum_age__isnull=False),
                name="spot_known_age_requires_minimum",
            ),
            models.CheckConstraint(
                condition=Q(typical_duration_minutes__gte=1),
                name="spot_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(bad_weather_suitable=False) | Q(indoor=True),
                name="spot_bad_weather_requires_indoor",
            ),
            models.UniqueConstraint(
                fields=("tourapi_id",),
                condition=~Q(tourapi_id=""),
                name="spot_tourapi_nonblank_uniq",
            ),
            models.UniqueConstraint(
                fields=("khoa_beach_code",),
                condition=~Q(khoa_beach_code=""),
                name="spot_khoa_code_nonblank_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("type", "region"), name="spot_type_region_idx"),
            models.Index(fields=("tourapi_id",), name="spot_tourapi_idx"),
            models.Index(fields=("khoa_beach_code",), name="spot_khoa_beach_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not _finite_in_range(self.lat, minimum=-90, maximum=90):
            errors["lat"] = "Latitude must be finite and between -90 and 90."
        if not _finite_in_range(self.lng, minimum=-180, maximum=180):
            errors["lng"] = "Longitude must be finite and between -180 and 180."
        if self.bad_weather_suitable and not self.indoor:
            errors["bad_weather_suitable"] = (
                "Bad-weather fallback must be explicitly indoor."
            )
        if self.age_policy_known and self.minimum_age is None:
            errors["minimum_age"] = (
                "A known age policy requires an explicit minimum age, including zero."
            )
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.maximum_age < self.minimum_age
        ):
            errors["maximum_age"] = "Maximum age cannot be below minimum age."
        feature_items = (
            self.preference_features.items()
            if isinstance(self.preference_features, dict)
            else ()
        )
        if not isinstance(self.preference_features, dict) or any(
            not isinstance(name, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
            for name, value in feature_items
        ):
            errors["preference_features"] = (
                "Preference features must map names to finite values from 0 to 1."
            )
        if not _valid_opening_windows(self.opening_windows):
            errors["opening_windows"] = (
                "Opening windows must be start/end minute objects within one day."
            )
        if errors:
            raise ValidationError(errors)


def _valid_opening_windows(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for window in value:
        if not isinstance(window, dict):
            return False
        start = window.get("start_minute")
        end = window.get("end_minute")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start < end <= 1_440
        ):
            return False
    return True


def _finite_in_range(value: object, *, minimum: float, maximum: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and minimum <= float(value) <= maximum


class NearbyFacility(models.Model):
    spot = models.ForeignKey(WaterSpot, on_delete=models.CASCADE)
    type = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    lat = models.FloatField()
    lng = models.FloatField()
    tag = models.CharField(max_length=100, blank=True)
    distance_min = models.IntegerField(help_text="Distance in minutes")


class CatchGuide(models.Model):
    spot = models.ForeignKey(WaterSpot, on_delete=models.CASCADE)
    species = models.CharField(max_length=100)
    banned_species = models.CharField(max_length=100, blank=True)
    best_time = models.CharField(max_length=100, blank=True)
    season_restriction = models.CharField(max_length=200, blank=True)


class HotspringDetail(models.Model):
    spot = models.OneToOneField(WaterSpot, on_delete=models.CASCADE)
    minerals = models.CharField(max_length=255, blank=True)
    benefits = models.CharField(max_length=255, blank=True)
