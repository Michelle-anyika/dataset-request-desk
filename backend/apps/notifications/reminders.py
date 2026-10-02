"""Reminders, escalations, deadline warnings and the email outbox, run by ``manage.py send_reminders``.

Idempotent: every decision is based on the notifications that already exist, so running it every minute
never sends anything extra. The checks are done in SQL for all requests at once (a fixed number of queries
however many requests are open); per-request work happens only for requests that actually need a message.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Count, Exists, F, Max, OuterRef, Q

from apps.core.dates import business_date
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.services import active_operators, delivering_operator, send_pending_emails
from apps.requests_desk.models import DatasetRequest, RequestStatus

K = NotificationKind
REMINDER_INTERVAL = timedelta(days=3)
MAX_REMINDERS = 3
DEADLINE_WARNING_DAYS = 2
OPEN_STATUSES = (RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS, RequestStatus.REJECTED)


@dataclass
class ReminderReport:
    reminders: int = 0
    escalations: int = 0
    deadline_warnings: int = 0
    emails_sent: int = 0


def send_reminders(*, now: datetime) -> ReminderReport:
    report = ReminderReport()
    new = _review_reminders(now, report) + _deadline_warnings(now, report)
    Notification.objects.bulk_create(new)
    report.emails_sent = send_pending_emails()
    return report


def _review_reminders(now: datetime, report: ReminderReport) -> list[Notification]:
    # Only notifications since the current delivery count: a re-delivery after rework starts again.
    since_delivery = Q(notifications__created_at__gte=F("status_changed_at"))
    reminders = since_delivery & Q(notifications__kind=K.REVIEW_REMINDER)
    escalation = Notification.objects.filter(
        request=OuterRef("pk"), kind=K.REVIEW_ESCALATION, created_at__gte=OuterRef("status_changed_at")
    )
    waiting = (
        DatasetRequest.objects.filter(
            status=RequestStatus.DELIVERED, status_changed_at__lte=now - REMINDER_INTERVAL
        )
        .annotate(
            reminder_count=Count("notifications", filter=reminders),
            last_reminder_at=Max("notifications__created_at", filter=reminders),
            escalated=Exists(escalation),
        )
        .select_related("client")
    )

    new = []
    for request in waiting:
        if now - (request.last_reminder_at or request.status_changed_at) < REMINDER_INTERVAL:
            continue
        if request.reminder_count < MAX_REMINDERS:
            new.append(
                Notification(
                    recipient=request.client, request=request, kind=K.REVIEW_REMINDER, created_at=now
                )
            )
            report.reminders += 1
        elif not request.escalated:
            operator = delivering_operator(request)
            for user in [operator] if operator else active_operators():
                new.append(
                    Notification(recipient=user, request=request, kind=K.REVIEW_ESCALATION, created_at=now)
                )
            report.escalations += 1
    return new


def _deadline_warnings(now: datetime, report: ReminderReport) -> list[Notification]:
    due = list(
        DatasetRequest.objects.filter(
            status__in=OPEN_STATUSES, deadline__lte=business_date(now) + timedelta(days=DEADLINE_WARNING_DAYS)
        ).exclude(notifications__kind=K.DEADLINE_APPROACHING)
    )
    if not due:
        return []
    operators = list(active_operators())
    report.deadline_warnings = len(due)
    return [
        Notification(recipient=operator, request=request, kind=K.DEADLINE_APPROACHING, created_at=now)
        for request in due
        for operator in operators
    ]
