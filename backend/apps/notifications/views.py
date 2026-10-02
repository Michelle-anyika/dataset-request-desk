from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationFilterSerializer,
    NotificationSerializer,
    UnreadSummarySerializer,
)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The current user's notifications. Anyone else's are "not found"."""

    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return Notification.objects.none()
        queryset = Notification.objects.filter(recipient=self.request.user).select_related("request")
        if self.action == "list":
            filters = NotificationFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            if filters.validated_data.get("unread") == "true":
                queryset = queryset.filter(read_at__isnull=True)
        return queryset

    @extend_schema(parameters=[NotificationFilterSerializer])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses={200: UnreadSummarySerializer})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Unread count for the notification bell."""
        return Response({"unread": self.get_queryset().filter(read_at__isnull=True).count()})

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={204: None})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)
