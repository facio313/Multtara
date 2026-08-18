from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from services.public_urls import public_https_url


class SoundProfile(models.Model):
    spot = models.ForeignKey('spots.WaterSpot', on_delete=models.CASCADE)
    sound_type = models.CharField(max_length=100)
    asmr_score = models.FloatField(null=True, blank=True)
    audio_url = models.URLField(blank=True)

class SpotAnalytics(models.Model):
    spot = models.OneToOneField('spots.WaterSpot', on_delete=models.CASCADE)
    avg_water_temp_5y = models.FloatField(null=True, blank=True)
    quality_trend = models.CharField(max_length=100, blank=True)
    crowd_trend = models.CharField(max_length=100, blank=True)
    best_season = models.CharField(max_length=100, blank=True)

class TripMemory(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    spot = models.ForeignKey('spots.WaterSpot', on_delete=models.CASCADE)
    photo_url = models.URLField(blank=True)
    taken_at = models.DateTimeField()
    estimated_location = models.CharField(max_length=200, blank=True)

    def clean(self) -> None:
        super().clean()
        if not self.photo_url:
            return
        sanitized = public_https_url(self.photo_url)
        if not sanitized:
            raise ValidationError(
                {"photo_url": "Photo URL must be a public HTTPS URL."}
            )
        # Discard query strings and fragments before they can become persisted
        # browser links or retain accidentally supplied credentials.
        self.photo_url = sanitized

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
