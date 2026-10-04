from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.catalog.import_service import ImportFailed
from apps.catalog.serializers import ImportUploadSerializer
from apps.catalog.spreadsheet import export_lines
from apps.core.idempotency import idempotent
from apps.core.permissions import IsAdmin
from apps.requests_desk.request_import import import_requests


class InvalidRequestFile(exceptions.APIException):
    """The whole file was refused (not a per-row problem), with the reason as the message."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_file"


class RowResultSerializer(serializers.Serializer):
    row = serializers.IntegerField(help_text="Line in the file (the header is line 1).")
    reference = serializers.CharField(help_text="The spreadsheet's reference for this request.")
    action = serializers.ChoiceField(
        choices=["create", "unchanged", "skip"],
        help_text="create: new (or will be, in a preview); unchanged: imported before; skip: see reason.",
    )
    reason_code = serializers.CharField(help_text="Why the row is skipped; empty otherwise.")
    message = serializers.CharField(help_text="The reason, readable.")
    client_email = serializers.CharField()
    task_name = serializers.CharField(help_text="As it will be stored (normalised).")
    status = serializers.CharField()


class RequestImportReportSerializer(serializers.Serializer):
    create = serializers.IntegerField()
    unchanged = serializers.IntegerField()
    skip = serializers.IntegerField()
    rows = RowResultSerializer(many=True)


class RequestImportViewSet(viewsets.ViewSet):
    """Migrate the spreadsheet's requests (admins). Preview first: nothing is saved until commit."""

    permission_classes = [*viewsets.ViewSet.permission_classes, IsAdmin]
    parser_classes = [MultiPartParser]

    def _run(self, request, *, commit: bool):
        upload = ImportUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        file = upload.validated_data["file"]
        try:
            report = import_requests(export_lines(file.file, file.name), admin=request.user, commit=commit)
        except ImportFailed as exc:
            raise InvalidRequestFile(str(exc)) from exc
        return report.as_dict()

    @extend_schema(
        request={"multipart/form-data": ImportUploadSerializer},
        responses={201: RequestImportReportSerializer},
    )
    @idempotent()
    def create(self, request):
        """Import the file: create the rows that pass, report the rest. Re-running creates nothing."""
        return Response(self._run(request, commit=True), status=status.HTTP_201_CREATED)

    @extend_schema(
        request={"multipart/form-data": ImportUploadSerializer},
        responses={200: RequestImportReportSerializer},
    )
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """What importing the file would do, row by row. Saves nothing."""
        return Response(self._run(request, commit=False))
