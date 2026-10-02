from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from apps.catalog.models import Episode, ImportBatch, ImportRowIssue, IssueSeverity, Quality
from apps.catalog.normalise import normalise_task_name
from apps.core.query import QueryParamsSerializer

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


class IssueFilterSerializer(QueryParamsSerializer):
    severity = serializers.ChoiceField(choices=IssueSeverity.choices, required=False)
    reason_code = serializers.CharField(max_length=50, required=False)


class EpisodeSerializer(serializers.ModelSerializer):
    assigned_request = serializers.UUIDField(
        read_only=True, allow_null=True, help_text="The request this episode is actively assigned to, if any."
    )

    class Meta:
        model = Episode
        fields = [
            "id",
            "episode_id",
            "robot_id",
            "task_name",
            "recorded_at",
            "duration_seconds",
            "operator_name",
            "quality",
            "assigned_request",
        ]
        read_only_fields = fields


class EpisodeFilterSerializer(QueryParamsSerializer):
    ORDERINGS = [
        "-recorded_at",
        "recorded_at",
        "episode_id",
        "-episode_id",
        "duration_seconds",
        "-duration_seconds",
    ]

    task_name = serializers.CharField(max_length=120, required=False)
    quality = serializers.MultipleChoiceField(
        choices=Quality.choices,
        required=False,
        help_text="Repeat to allow several, e.g. quality=good&quality=usable.",
    )
    robot_id = serializers.CharField(max_length=32, required=False)
    # A choice, not a BooleanField: DRF reads a missing query boolean as False, which would hide every
    # available episode when no filter is given.
    available = serializers.ChoiceField(
        choices=["true", "false"], required=False, help_text="true: not assigned to any request right now."
    )
    ordering = serializers.ChoiceField(choices=ORDERINGS, required=False)

    def validate_task_name(self, value):
        return normalise_task_name(value)
