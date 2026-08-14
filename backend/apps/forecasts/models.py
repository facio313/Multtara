from django.db import models

class WaterForecast(models.Model):
    spot = models.ForeignKey('spots.WaterSpot', on_delete=models.CASCADE)
    forecast_date = models.DateField()
    predicted_index = models.FloatField()
    predicted_factors = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

class GoldenMoment(models.Model):
    spot = models.ForeignKey('spots.WaterSpot', on_delete=models.CASCADE)
    date = models.DateField()
    time = models.TimeField()
    type = models.CharField(max_length=100)
