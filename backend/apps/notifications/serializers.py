from rest_framework import serializers

from apps.notifications import messages
from apps.notifications.models import Notification
from apps.requests_desk.models import DatasetRequest


class NotificationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRequest
        fields = ["id", "task_name", "status"]


class NotificationSerializer(serializers.ModelSerializer):
    request = NotificationRequestSerializer(read_only=True)
    message = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "message", "request", "created_at", "read_at"]
        read_only_fields = fields

    def get_message(self, obj) -> str:
        return messages.subject(obj)


class UnreadSummarySerializer(serializers.Serializer):
    unread = serializers.IntegerField()
