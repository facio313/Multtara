from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    persona_type = models.CharField(max_length=50, blank=True)
    mood_state = models.CharField(max_length=50, blank=True)
    home_region = models.CharField(max_length=100, blank=True)

class UserActivity(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    spot = models.ForeignKey('spots.WaterSpot', on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    rating = models.IntegerField(null=True, blank=True)
    review_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Passport(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="passport_stamps",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="passport_stamps",
    )
    verified_at = models.DateTimeField(auto_now_add=True)
    badge_earned = models.JSONField(default=dict, blank=True)
    eco_action = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "spot"), name="unique_passport_visit"),
        ]
        ordering = ["-verified_at"]
