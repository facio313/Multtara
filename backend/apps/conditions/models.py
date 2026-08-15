from django.db import models

class WaterCondition(models.Model):
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="conditions",
    )
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
    marine_indices = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fetched_at"]

class ConditionScore(models.Model):
    ACTIVITIES = (
        ("swim", "Swim"),
        ("surf", "Surf"),
        ("relax", "Relax"),
        ("mudflat", "Mudflat"),
        ("onsen", "Onsen"),
        ("rafting", "Rafting"),
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="scores",
    )
    activity = models.CharField(max_length=100, choices=ACTIVITIES)
    score = models.FloatField()
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-computed_at"]
        unique_together = ("spot", "activity")

class CrowdLevel(models.Model):
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="crowd_levels",
    )
    predicted_level = models.CharField(max_length=50)
    recommended_time = models.CharField(max_length=100, blank=True)
    parking_availability = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
