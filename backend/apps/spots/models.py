from django.db import models

class WaterSpot(models.Model):
    SPOT_TYPES = (
        ("sea", "Sea"),
        ("pool", "Pool"),
        ("hotspring", "Hot Spring"),
        ("valley", "Valley"),
        ("lake", "Lake"),
        ("waterpark", "Waterpark"),
        ("waterfall", "Waterfall"),
        ("tidal_flat", "Tidal Flat"),
        ("riverside", "Riverside"),
    )
    type = models.CharField(max_length=20, choices=SPOT_TYPES)
    name = models.CharField(max_length=200)
    lat = models.FloatField()
    lng = models.FloatField()
    tourapi_id = models.CharField(max_length=100, blank=True)
    tags = models.JSONField(default=list, blank=True)
    livecam_url = models.URLField(blank=True)
    pet_allowed = models.BooleanField(default=False)
    accessibility = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    image_url = models.URLField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name

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
