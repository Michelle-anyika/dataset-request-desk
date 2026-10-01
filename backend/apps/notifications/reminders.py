"""Reminders, escalations, deadline warnings and email retries, run by ``manage.py send_reminders``.

Idempotent: every decision is based on the notifications that already exist, so running it twice, or every
hour, never sends anything extra.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.core.dates import business_date
from apps.notifications.models import EMAIL_KINDS, Notification, NotificationKind
from apps.notifications.services import active_operators, delivering_operator, send_emails
from apps.requests_desk.models import DatasetRequest, RequestStatus

K = NotificationKind
REMINDER_INTERVAL = timedelta(days=3)
MAX_REMINDERS = 3
DEADLINE_WARNING_DAYS = 2
EMAIL_RETRY_AFTER = timedelta(minutes=5)  # leave fresh emails to the on-commit sender
OPEN_STATUSES = (RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS, RequestStatus.REJECTED)


@dataclass
class ReminderReport:
    reminders: int = 0
    escalations: int = 0
    deadline_warnings: int = 0
    emails_retried: int = 0


def send_reminders(*, now: datetime) -> ReminderReport:
    report = ReminderReport()
    _review_reminders(now, report)
    _deadline_warnings(now, report)
    unsent = Notification.objects.filter(
        kind__in=EMAIL_KINDS, emailed_at__isnull=True, created_at__lte=now - EMAIL_RETRY_AFTER
    )
    report.emails_retried = send_emails(unsent)
    return report


def _review_reminders(now: datetime, report: ReminderReport) -> None:
    waiting = DatasetRequest.objects.filter(
        status=RequestStatus.DELIVERED, status_changed_at__lte=now - REMINDER_INTERVAL
    ).select_related("client")
    for request in waiting:
        # Only notifications since the current delivery count: a re-delivery after rework starts again.
        since_delivery = request.notifications.filter(created_at__gte=request.status_changed_at)
        reminders = since_delivery.filter(kind=K.REVIEW_REMINDER).order_by("-created_at")
        last = reminders.first()
        last_contact = last.created_at if last else request.status_changed_at
        if now - last_contact < REMINDER_INTERVAL:
            continue

        if reminders.count() < MAX_REMINDERS:
            new = [
                Notification(
                    recipient=request.client, request=request, kind=K.REVIEW_REMINDER, created_at=now
                )
            ]
            report.reminders += 1
        elif not since_delivery.filter(kind=K.REVIEW_ESCALATION).exists():
            operator = delivering_operator(request)
            recipients = [operator] if operator else list(active_operators())
            new = [
                Notification(recipient=user, request=request, kind=K.REVIEW_ESCALATION, created_at=now)
                for user in recipients
            ]
            report.escalations += 1
        else:
            continue
        created = Notification.objects.bulk_create(new)
        send_emails(Notification.objects.filter(pk__in=[n.pk for n in created]))


def _deadline_warnings(now: datetime, report: ReminderReport) -> None:
    due = DatasetRequest.objects.filter(
        status__in=OPEN_STATUSES, deadline__lte=business_date(now) + timedelta(days=DEADLINE_WARNING_DAYS)
    ).exclude(notifications__kind=K.DEADLINE_APPROACHING)
    operators = list(active_operators())
    for request in due:
        Notification.objects.bulk_create(
            [
                Notification(recipient=op, request=request, kind=K.DEADLINE_APPROACHING, created_at=now)
                for op in operators
            ]
        )
        report.deadline_warnings += 1
