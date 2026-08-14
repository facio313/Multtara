from rest_framework import serializers
from .models import WaterCondition, ConditionScore

class WaterConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterCondition
        fields = '__all__'

class ConditionScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConditionScore
        fields = '__all__'
