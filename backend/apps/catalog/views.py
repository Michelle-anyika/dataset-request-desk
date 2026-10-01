import io

from django.db.models import Exists, OuterRef
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.catalog.import_service import ImportFailed, import_episodes
from apps.catalog.models import ImportBatch, ImportStatus
from apps.catalog.serializers import (
    ImportBatchSerializer,
    ImportRowIssueSerializer,
    ImportUploadSerializer,
    IssueFilterSerializer,
)
from apps.core.permissions import IsOperator


class InvalidImportFile(exceptions.APIException):
    """The whole file was refused (not a per-field error), with the reason as the message."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_file"


class ImportBatchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Episode imports: upload an export, then browse each run's report and its row issues."""

    permission_classes = [*viewsets.GenericViewSet.permission_classes, IsOperator]
    serializer_class = ImportBatchSerializer
    # The only write is the file upload. (Parsers are chosen before the action is known, so this is per view.)
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        earlier_success = ImportBatch.objects.filter(
            file_sha256=OuterRef("file_sha256"),
            status=ImportStatus.COMPLETED,
            started_at__lt=OuterRef("started_at"),
        )
        return ImportBatch.objects.select_related("uploaded_by").annotate(
            previously_imported=Exists(earlier_success)
        )

    @extend_schema(
        request={"multipart/form-data": ImportUploadSerializer}, responses={201: ImportBatchSerializer}
    )
    def create(self, request):
        upload = ImportUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        file = upload.validated_data["file"]
        # utf-8-sig drops a byte-order mark if the export has one; newline="" lets the csv module see CRLF.
        lines = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
        try:
            batch = import_episodes(lines, file_name=file.name, uploaded_by=request.user)
        except ImportFailed as exc:
            raise InvalidImportFile(str(exc)) from exc
        report = self.get_queryset().get(pk=batch.pk)
        return Response(ImportBatchSerializer(report).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[IssueFilterSerializer], responses={200: ImportRowIssueSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def issues(self, request, pk=None):
        batch = self.get_object()
        filters = IssueFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        page = self.paginate_queryset(batch.issues.filter(**filters.validated_data))
        return self.get_paginated_response(ImportRowIssueSerializer(page, many=True).data)
