from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.idempotency import idempotent
from apps.core.openapi import error_response
from apps.core.permissions import IsClient, IsOperator
from apps.core.query import QueryParamsSerializer
from apps.requests_desk import assignments, services, workflow
from apps.requests_desk.models import Assignment, DatasetRequest
from apps.requests_desk.serializers import (
    AssignEpisodesSerializer,
    AssignmentFilterSerializer,
    AssignmentHistorySerializer,
    AssignmentSerializer,
    AssignResultSerializer,
    DatasetRequestSerializer,
    RequestEventSerializer,
    RequestFilterSerializer,
    TransitionSerializer,
)


class DatasetRequestViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = DatasetRequestSerializer

    def get_permissions(self):
        if self.action == "create":
            return [*super().get_permissions(), IsClient()]
        if self.action == "unassign" or (self.action == "assignments" and self.request.method == "POST"):
            return [*super().get_permissions(), IsOperator()]
        return super().get_permissions()

    def get_queryset(self):
        """Every read goes through here: a client's queryset only contains their own requests.

        Anything outside it is "not found" (404), so a client can't tell whether another
        client's request exists.
        """
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return DatasetRequest.objects.none()
        user = self.request.user
        # A correlated subquery, not JOIN + GROUP BY: PostgreSQL computes it only for the rows on the page,
        # and the pagination COUNT(*) leaves it out. (The GROUP BY version cost ~3 s a page at 100k requests.)
        active = (
            Assignment.objects.filter(request=OuterRef("pk"), released_at__isnull=True)
            .order_by()
            .values("request")
            .annotate(total=Count("id"))
            .values("total")
        )
        queryset = DatasetRequest.objects.select_related("client").annotate(
            active_assignment_count=Coalesce(Subquery(active, output_field=IntegerField()), 0)
        )
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

    @idempotent()
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.instance = services.submit_request(self.request.user, **serializer.validated_data)

    @extend_schema(
        request=TransitionSerializer,
        responses={
            200: DatasetRequestSerializer,
            409: error_response("Not a valid step from the current status, or too few episodes assigned."),
        },
        description="Move the request through its workflow. Allowed steps depend on status and role.",
    )
    @action(detail=True, methods=["post"], url_path="transitions")
    @idempotent()
    def transitions(self, request, pk=None):
        dataset_request = self.get_object()  # scoped: another client's request is 404
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = workflow.transition(dataset_request, actor=request.user, **serializer.validated_data)
        return Response(DatasetRequestSerializer(updated).data)

    @extend_schema(responses={200: RequestEventSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        """Status history, oldest first, paginated (it grows with every rework). Append-only."""
        QueryParamsSerializer(data=request.query_params).is_valid(raise_exception=True)
        dataset_request = self.get_object()  # scoped: another client's request is 404
        page = self.paginate_queryset(dataset_request.events.select_related("changed_by"))
        return self.get_paginated_response(RequestEventSerializer(page, many=True).data)

    @extend_schema(
        methods=["GET"],
        parameters=[AssignmentFilterSerializer],
        responses={200: AssignmentHistorySerializer(many=True)},
        description="Episodes assigned to the request. Clients see what is currently assigned to their own.",
    )
    @extend_schema(
        methods=["POST"],
        request=AssignEpisodesSerializer,
        responses={
            201: AssignResultSerializer,
            409: error_response("The request is not in progress, or an episode is assigned elsewhere."),
        },
        description="Assign episodes (operators and admins). All or nothing: any problem assigns none.",
    )
    @action(detail=True, methods=["get", "post"], url_path="assignments")
    @idempotent("POST")
    def assignments(self, request, pk=None):
        dataset_request = self.get_object()  # scoped: another client's request is 404
        if request.method == "POST":
            payload = AssignEpisodesSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            assigned = assignments.assign_episodes(
                dataset_request, payload.validated_data["episode_ids"], actor=request.user
            )
            result = {
                "assigned": assigned,
                "assigned_count": assignments.active_count(dataset_request),
                "episodes_requested": dataset_request.episodes_requested,
            }
            return Response(result, status=status.HTTP_201_CREATED)

        filters = AssignmentFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        is_staff = IsOperator().has_permission(request, self)
        rows = dataset_request.assignments.select_related("episode", "assigned_by", "released_by")
        if not (is_staff and filters.validated_data.get("history") == "true"):
            rows = rows.filter(released_at__isnull=True)
        serializer_class = AssignmentHistorySerializer if is_staff else AssignmentSerializer
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(serializer_class(page, many=True).data)

    @extend_schema(
        request=None,
        responses={204: None, 409: error_response("The request is not in progress.")},
        description="Release an episode (operators and admins).",
    )
    @action(detail=True, methods=["delete"], url_path=r"assignments/(?P<episode_id>[^/]+)")
    def unassign(self, request, pk=None, episode_id=None):
        assignments.unassign_episode(self.get_object(), episode_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
