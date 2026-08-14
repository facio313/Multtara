from django.contrib import admin
from .models import WaterCondition, ConditionScore, CrowdLevel

admin.site.register(WaterCondition)
admin.site.register(ConditionScore)
admin.site.register(CrowdLevel)
