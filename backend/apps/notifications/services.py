"""Creating notifications and sending their emails (PLAN.md §7.4).

Status-change notifications are created inside the workflow's transaction, so a notification exists exactly
when its status change does. Emails are an outbox: the request only records them, and the scheduler sends
pending ones every minute. A request never waits for a mail server, a rolled-back change never emails anyone,
and a failed send stays pending (``emailed_at`` empty) until the next run.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import Role
from apps.notifications import messages
from apps.notifications.models import EMAIL_KINDS, Notification, NotificationKind
from apps.requests_desk.models import RequestStatus

logger = logging.getLogger(__name__)
S = RequestStatus


def active_operators():
    return get_user_model().objects.filter(role=Role.OPERATOR, is_active=True)


def delivering_operator(request):
    """Who made the latest delivery: they hear about the client's decision."""
    event = (
        request.events.filter(to_status=S.DELIVERED)
        .select_related("changed_by")
        .order_by("-changed_at")
        .first()
    )
    return event.changed_by if event and event.changed_by.is_active else None


def notify_status_change(request, event) -> None:
    """Called by the workflow, inside its transaction, for every status change."""
    if event.to_status == S.SUBMITTED:
        recipients, kind = list(active_operators()), NotificationKind.REQUEST_SUBMITTED
    elif event.to_status == S.DELIVERED:
        recipients, kind = [request.client], NotificationKind.REQUEST_DELIVERED
    elif event.to_status in (S.ACCEPTED, S.REJECTED):
        operator = delivering_operator(request)
        recipients = [operator] if operator else list(active_operators())
        kind = (
            NotificationKind.DELIVERY_ACCEPTED
            if event.to_status == S.ACCEPTED
            else NotificationKind.DELIVERY_REJECTED
        )
    else:
        return

    Notification.objects.bulk_create(
        [Notification(recipient=user, request=request, event=event, kind=kind) for user in recipients]
    )


def send_pending_emails() -> int:
    """Send every notification email not sent yet (the outbox). Returns how many were sent."""
    return send_emails(Notification.objects.filter(kind__in=EMAIL_KINDS, emailed_at__isnull=True))


def send_emails(notifications) -> int:
    """Send each notification's email once. Returns how many were sent; failures are retried later."""
    sent = 0
    for notification in notifications.select_related("recipient", "request", "event"):
        if notification.emailed_at is not None or notification.kind not in EMAIL_KINDS:
            continue
        try:
            send_mail(
                subject=messages.subject(notification),
                message=messages.email_body(notification),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.recipient.email],
            )
        except Exception:
            # Never let email trouble break the workflow; the scheduler retries unsent notifications.
            logger.exception("Notification email failed", extra={"notification_id": notification.pk})
            continue
        Notification.objects.filter(pk=notification.pk).update(emailed_at=timezone.now())
        sent += 1
    return sent
