from rest_framework import serializers
from .models import WaterSpot

class WaterSpotSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterSpot
        fields = '__all__'
