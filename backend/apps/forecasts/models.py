from django.db import models

class WaterForecast(models.Model):
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="forecasts",
    )
    forecast_date = models.DateField()
    predicted_index = models.FloatField()
    predicted_factors = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["forecast_date"]
        unique_together = ("spot", "forecast_date")

class GoldenMoment(models.Model):
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="golden_moments",
    )
    date = models.DateField()
    time = models.TimeField()
    type = models.CharField(max_length=100)

    class Meta:
        ordering = ["date", "time"]
        unique_together = ("spot", "date", "type")
