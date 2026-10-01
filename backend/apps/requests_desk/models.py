import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class RequestStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    IN_PROGRESS = "in_progress", "In progress"
    DELIVERED = "delivered", "Delivered"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class DatasetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dataset_requests"
    )
    task_name = models.CharField(max_length=120)  # normalised, see apps.catalog.normalise
    episodes_requested = models.PositiveIntegerField()
    deadline = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=RequestStatus.choices, default=RequestStatus.SUBMITTED)
    # When the current status was entered: drives "awaiting decision for N days" and reminders.
    status_changed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dataset_requests"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(episodes_requested__gt=0), name="requests_count_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RequestStatus.values), name="requests_status_valid"
            ),
        ]
        indexes = [
            models.Index(fields=["client", "status"], name="requests_client_status_idx"),
            models.Index(fields=["status", "deadline"], name="requests_status_deadline_idx"),
            models.Index(fields=["status", "status_changed_at"], name="requests_status_changed_idx"),
        ]

    def __str__(self):
        return f"{self.task_name} x{self.episodes_requested} ({self.status})"


class RequestStatusEvent(models.Model):
    """Append-only audit trail: who changed a request's status, when, and why."""

    request = models.ForeignKey(DatasetRequest, on_delete=models.PROTECT, related_name="events")
    # NULL, not "", for the submission event: there was no previous status, and an empty string
    # would pretend there was one.
    from_status = models.CharField(  # noqa: DJ001
        max_length=16, choices=RequestStatus.choices, null=True, blank=True
    )
    to_status = models.CharField(max_length=16, choices=RequestStatus.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    changed_at = models.DateTimeField(default=timezone.now)
    comment = models.TextField(blank=True)

    class Meta:
        db_table = "request_status_events"
        ordering = ["changed_at", "id"]
        indexes = [
            models.Index(fields=["request", "changed_at"], name="events_request_time_idx"),
            models.Index(fields=["to_status", "changed_at"], name="events_status_time_idx"),
        ]

    def __str__(self):
        return f"{self.from_status or '-'} -> {self.to_status} at {self.changed_at:%Y-%m-%d %H:%M}"
