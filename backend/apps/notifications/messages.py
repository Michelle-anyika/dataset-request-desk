"""Wording for notifications: one subject line for the inbox, plus an email body with a link."""

from django.conf import settings

from apps.notifications.models import NotificationKind as K


def request_link(request) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/requests/{request.id}"


def subject(notification) -> str:
    request = notification.request
    task = f"'{request.task_name}'"
    return {
        K.REQUEST_SUBMITTED: (
            f"New request: {request.episodes_requested} {task} episodes due {request.deadline}"
        ),
        K.REQUEST_DELIVERED: f"Your {task} dataset is ready for review",
        K.DELIVERY_ACCEPTED: f"The {task} delivery was accepted",
        K.DELIVERY_REJECTED: f"The {task} delivery was rejected",
        K.REVIEW_REMINDER: f"Your {task} delivery is waiting for your decision",
        K.REVIEW_ESCALATION: f"No decision yet on the {task} delivery: please follow up with the client",
        K.DEADLINE_APPROACHING: f"The {task} request is due {request.deadline} and not delivered yet",
    }[notification.kind]


def email_body(notification) -> str:
    lines = [subject(notification) + "."]
    if notification.kind == K.DELIVERY_REJECTED and notification.event and notification.event.comment:
        lines.append(f"Reason given: {notification.event.comment}")
    if notification.kind in (K.REQUEST_DELIVERED, K.REVIEW_REMINDER):
        lines.append("Please review the episodes and accept or reject the delivery.")
    lines += ["", request_link(notification.request), "", "Dataset Request Desk"]
    return "\n".join(lines)
