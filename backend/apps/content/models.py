from django.db import models


class SoundProfile(models.Model):
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="sound_profiles",
    )
    sound_type = models.CharField(max_length=100)
    asmr_score = models.FloatField(null=True, blank=True)
    audio_url = models.URLField(blank=True)

    class Meta:
        ordering = ["-asmr_score"]


class SpotAnalytics(models.Model):
    spot = models.OneToOneField(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="analytics",
    )
    avg_water_temp_5y = models.FloatField(null=True, blank=True)
    quality_trend = models.CharField(max_length=100, blank=True)
    crowd_trend = models.CharField(max_length=100, blank=True)
    best_season = models.CharField(max_length=100, blank=True)


class TripMemory(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trip_memories",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="trip_memories",
    )
    photo_url = models.CharField(max_length=500, blank=True)
    taken_at = models.DateTimeField()
    estimated_location = models.CharField(max_length=200, blank=True)
    condition_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-taken_at"]
