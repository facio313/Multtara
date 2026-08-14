from rest_framework import serializers
from .models import WaterForecast

class WaterForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterForecast
        fields = '__all__'
