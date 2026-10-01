from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from apps.accounts.models import Role
from apps.core.permissions import IsClient
from apps.requests_desk import services
from apps.requests_desk.models import DatasetRequest
from apps.requests_desk.serializers import DatasetRequestSerializer, RequestFilterSerializer


class DatasetRequestViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = DatasetRequestSerializer

    def get_permissions(self):
        if self.action == "create":
            return [*super().get_permissions(), IsClient()]
        return super().get_permissions()

    def get_queryset(self):
        """Every read goes through here: a client's queryset only contains their own requests.

        Anything outside it is "not found" (404), so a client can't tell whether another
        client's request exists.
        """
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return DatasetRequest.objects.none()
        user = self.request.user
        queryset = DatasetRequest.objects.select_related("client")
        if user.role == Role.CLIENT:
            queryset = queryset.filter(client=user)
        if self.action == "list":
            queryset = self._apply_filters(queryset, is_client=user.role == Role.CLIENT)
        return queryset

    def _apply_filters(self, queryset, *, is_client):
        filters = RequestFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        if "status" in params:
            queryset = queryset.filter(status=params["status"])
        if "client" in params and not is_client:  # a client's scope is fixed; the filter can't widen it
            queryset = queryset.filter(client_id=params["client"])
        return queryset.order_by(params.get("ordering", "-created_at"), "-created_at")

    @extend_schema(parameters=[RequestFilterSerializer])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.instance = services.submit_request(self.request.user, **serializer.validated_data)
