from rest_framework import mixins, viewsets

from apps.core.permissions import IsClient
from apps.requests_desk import services
from apps.requests_desk.models import DatasetRequest
from apps.requests_desk.serializers import DatasetRequestSerializer


class DatasetRequestViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = DatasetRequestSerializer
    queryset = DatasetRequest.objects.select_related("client")

    def get_permissions(self):
        if self.action == "create":
            return [*super().get_permissions(), IsClient()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.instance = services.submit_request(self.request.user, **serializer.validated_data)
