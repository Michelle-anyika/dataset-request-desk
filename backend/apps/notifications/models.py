from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationKind(models.TextChoices):
    REQUEST_SUBMITTED = "request_submitted", "Request submitted"
    REQUEST_DELIVERED = "request_delivered", "Request delivered"
    DELIVERY_ACCEPTED = "delivery_accepted", "Delivery accepted"
    DELIVERY_REJECTED = "delivery_rejected", "Delivery rejected"
    REVIEW_REMINDER = "review_reminder", "Review reminder"
    REVIEW_ESCALATION = "review_escalation", "Review escalation"
    DEADLINE_APPROACHING = "deadline_approaching", "Deadline approaching"


# Also emailed: the recipient may not be logged in (decision #11).
EMAIL_KINDS = {
    NotificationKind.REQUEST_DELIVERED,
    NotificationKind.DELIVERY_REJECTED,
    NotificationKind.REVIEW_REMINDER,
    NotificationKind.REVIEW_ESCALATION,
}


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    request = models.ForeignKey(
        "requests_desk.DatasetRequest", on_delete=models.CASCADE, related_name="notifications"
    )
    # The status change behind it; empty for reminders and deadline warnings.
    event = models.ForeignKey(
        "requests_desk.RequestStatusEvent", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=32, choices=NotificationKind.choices)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)  # NULL = unread
    emailed_at = models.DateTimeField(null=True, blank=True)  # NULL for an email kind = not sent yet, retried

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "read_at", "created_at"], name="notifications_inbox_idx"),
            models.Index(fields=["request", "kind"], name="notifications_request_kind_idx"),
        ]

    def __str__(self):
        return f"{self.kind} for {self.recipient_id}"
