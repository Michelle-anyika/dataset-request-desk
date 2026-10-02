from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.catalog.models import Episode
from apps.catalog.normalise import normalise_task_name
from apps.core.dates import business_today
from apps.requests_desk.assignments import MAX_EPISODES_PER_CALL, active_count
from apps.requests_desk.models import Assignment, DatasetRequest, RequestStatus, RequestStatusEvent

MAX_EPISODES_PER_REQUEST = 1_000_000


class RequestClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "full_name", "organisation"]


class DatasetRequestSerializer(serializers.ModelSerializer):
    client = RequestClientSerializer(read_only=True)
    episodes_requested = serializers.IntegerField(min_value=1, max_value=MAX_EPISODES_PER_REQUEST)
    notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    assigned_count = serializers.SerializerMethodField(
        help_text="Episodes currently assigned to the request."
    )

    class Meta:
        model = DatasetRequest
        fields = [
            "id",
            "client",
            "task_name",
            "episodes_requested",
            "assigned_count",
            "deadline",
            "notes",
            "status",
            "status_changed_at",
            "created_at",
        ]
        read_only_fields = ["id", "client", "status", "status_changed_at", "created_at"]

    def get_assigned_count(self, obj) -> int:
        # Lists annotate the count in SQL (no query per row); single objects fall back to one query.
        annotated = getattr(obj, "active_assignment_count", None)
        return annotated if annotated is not None else active_count(obj)

    def validate_task_name(self, value):
        value = normalise_task_name(value)
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate_deadline(self, value):
        if value < business_today():
            raise serializers.ValidationError("The deadline can't be in the past.")
        return value


class RequestFilterSerializer(serializers.Serializer):
    """Query parameters for the request list. Unknown values are a 400, not silently ignored."""

    ORDERINGS = [
        "created_at",
        "-created_at",
        "deadline",
        "-deadline",
        "status_changed_at",
        "-status_changed_at",
    ]

    status = serializers.ChoiceField(choices=RequestStatus.choices, required=False)
    client = serializers.UUIDField(
        required=False, help_text="Operators and admins only; ignored for clients."
    )
    ordering = serializers.ChoiceField(choices=ORDERINGS, required=False)


class TransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=RequestStatus.choices)
    comment = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")


class EventAuthorSerializer(serializers.ModelSerializer):
    """Name and role only: clients see who acted, never staff email addresses or ids."""

    class Meta:
        model = get_user_model()
        fields = ["full_name", "role"]


class RequestEventSerializer(serializers.ModelSerializer):
    changed_by = EventAuthorSerializer(read_only=True)

    class Meta:
        model = RequestStatusEvent
        fields = ["from_status", "to_status", "changed_by", "changed_at", "comment"]
        read_only_fields = fields


class AssignEpisodesSerializer(serializers.Serializer):
    episode_ids = serializers.ListField(
        child=serializers.CharField(max_length=32), allow_empty=False, max_length=MAX_EPISODES_PER_CALL
    )


class AssignResultSerializer(serializers.Serializer):
    assigned = serializers.ListField(child=serializers.CharField())
    assigned_count = serializers.IntegerField()
    episodes_requested = serializers.IntegerField()


class AssignedEpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Episode
        fields = ["episode_id", "robot_id", "task_name", "recorded_at", "duration_seconds", "quality"]
        read_only_fields = fields


class AssignmentSerializer(serializers.ModelSerializer):
    """What a client sees: the episodes they are getting."""

    episode = AssignedEpisodeSerializer(read_only=True)

    class Meta:
        model = Assignment
        fields = ["episode", "assigned_at"]
        read_only_fields = fields


class AssignmentHistorySerializer(AssignmentSerializer):
    """What staff see: including released assignments and who made each change."""

    assigned_by = EventAuthorSerializer(read_only=True)
    released_by = EventAuthorSerializer(read_only=True)

    class Meta(AssignmentSerializer.Meta):
        fields = ["episode", "assigned_at", "assigned_by", "released_at", "released_by"]
        read_only_fields = fields
