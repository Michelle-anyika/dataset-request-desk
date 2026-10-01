from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.normalise import normalise_task_name
from apps.requests_desk.models import DatasetRequest

MAX_EPISODES_PER_REQUEST = 1_000_000


class RequestClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "full_name", "organisation"]


class DatasetRequestSerializer(serializers.ModelSerializer):
    client = RequestClientSerializer(read_only=True)
    episodes_requested = serializers.IntegerField(min_value=1, max_value=MAX_EPISODES_PER_REQUEST)
    notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)

    class Meta:
        model = DatasetRequest
        fields = [
            "id",
            "client",
            "task_name",
            "episodes_requested",
            "deadline",
            "notes",
            "status",
            "status_changed_at",
            "created_at",
        ]
        read_only_fields = ["id", "client", "status", "status_changed_at", "created_at"]

    def validate_task_name(self, value):
        value = normalise_task_name(value)
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate_deadline(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("The deadline can't be in the past.")
        return value
