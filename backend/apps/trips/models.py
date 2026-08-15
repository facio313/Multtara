from django.db import models

class Itinerary(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    start_point = models.CharField(max_length=200)
    transport = models.CharField(max_length=100)
    is_day_trip = models.BooleanField(default=True)
    party_size = models.IntegerField(default=1)
    budget = models.IntegerField(null=True, blank=True)
    schedule = models.JSONField(default=list, blank=True)

class SafetyCard(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="safety_cards",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="safety_cards",
    )
    condition_snapshot = models.JSONField(default=dict, blank=True)
    risk_factors = models.JSONField(default=list, blank=True)
    nearest_safety_facility = models.CharField(max_length=200, blank=True)
    shared_with = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
