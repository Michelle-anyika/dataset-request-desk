from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from apps.catalog.models import ImportBatch, ImportRowIssue, IssueSeverity

ALLOWED_EXTENSIONS = {".csv"}


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        if Path(upload.name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError("Upload the export as a .csv file.")
        if upload.size > settings.IMPORT_MAX_UPLOAD_BYTES:
            limit_mb = settings.IMPORT_MAX_UPLOAD_BYTES / (1024 * 1024)
            raise serializers.ValidationError(f"The file is larger than {limit_mb:g} MB.")
        return upload


class UploaderSerializer(serializers.Serializer):
    full_name = serializers.CharField()


class ImportBatchSerializer(serializers.ModelSerializer):
    uploaded_by = UploaderSerializer(read_only=True)
    previously_imported = serializers.BooleanField(
        read_only=True, help_text="The same file (by SHA-256) was imported successfully before."
    )

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "file_name",
            "status",
            "total_rows",
            "created_count",
            "updated_count",
            "unchanged_count",
            "skipped_count",
            "fixed_count",
            "error_message",
            "previously_imported",
            "uploaded_by",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class ImportRowIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowIssue
        fields = ["row_number", "episode_id", "severity", "reason_code", "message", "raw_row"]
        read_only_fields = fields


class IssueFilterSerializer(serializers.Serializer):
    severity = serializers.ChoiceField(choices=IssueSeverity.choices, required=False)
    reason_code = serializers.CharField(max_length=50, required=False)
