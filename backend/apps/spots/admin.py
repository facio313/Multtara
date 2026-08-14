from django.contrib import admin
from .models import WaterSpot, NearbyFacility, CatchGuide, HotspringDetail

admin.site.register(WaterSpot)
admin.site.register(NearbyFacility)
admin.site.register(CatchGuide)
admin.site.register(HotspringDetail)
