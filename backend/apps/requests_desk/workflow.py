"""The request status workflow: the only place that changes a request's status.

    submitted → in_progress → delivered → accepted
                                        ↘ rejected → in_progress (rework)

Each allowed transition names who owns the step and any guard. Anything else is refused.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions, status

from apps.accounts.models import Role
from apps.notifications.services import notify_status_change
from apps.requests_desk.assignments import active_count
from apps.requests_desk.models import DatasetRequest, RequestStatus, RequestStatusEvent

S = RequestStatus


class InvalidTransition(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invalid_transition"

    def __init__(self, current, target):
        super().__init__(f"A request can't move from {current} to {target}.")


class TransitionNotAllowed(exceptions.PermissionDenied):
    default_code = "transition_not_allowed"

    def __init__(self, target):
        super().__init__(f"Your role can't move a request to {target}.")


class NotEnoughEpisodes(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "not_enough_episodes"

    def __init__(self, assigned, requested):
        super().__init__(f"Only {assigned} of {requested} requested episodes are assigned.")
        self.details = {"assigned": assigned, "requested": requested}


def _is_staff(user, request) -> bool:
    return user.role in (Role.OPERATOR, Role.ADMIN)


def _is_owner(user, request) -> bool:
    # Only the client who owns the request decides on its delivery; staff can't decide for them.
    return user.role == Role.CLIENT and request.client_id == user.pk


def _enough_episodes_assigned(request) -> None:
    assigned = active_count(request)
    if assigned < request.episodes_requested:
        raise NotEnoughEpisodes(assigned, request.episodes_requested)


def _reason_given(comment: str) -> None:
    if not comment.strip():
        raise exceptions.ValidationError({"comment": ["Give a reason when rejecting a delivery."]})


@dataclass(frozen=True)
class Step:
    may_perform: Callable  # (user, request) -> bool
    guard: Callable | None = None  # (request) -> None, raises when the step can't happen yet
    needs_reason: bool = False


TRANSITIONS: dict[tuple[str, str], Step] = {
    (S.SUBMITTED, S.IN_PROGRESS): Step(_is_staff),
    (S.IN_PROGRESS, S.DELIVERED): Step(_is_staff, guard=_enough_episodes_assigned),
    (S.DELIVERED, S.ACCEPTED): Step(_is_owner),
    (S.DELIVERED, S.REJECTED): Step(_is_owner, needs_reason=True),
    (S.REJECTED, S.IN_PROGRESS): Step(_is_staff),
}


@transaction.atomic
def transition(request: DatasetRequest, *, to_status: str, actor, comment: str = "") -> DatasetRequest:
    """Move a request to ``to_status`` on behalf of ``actor``, recording who did it and when.

    The row is locked first, so two people acting on the same request at once are handled one after the
    other, and the second sees the first one's result.
    """
    request = DatasetRequest.objects.select_for_update().get(pk=request.pk)

    step = TRANSITIONS.get((request.status, to_status))
    if step is None:
        raise InvalidTransition(request.status, to_status)
    if not step.may_perform(actor, request):
        raise TransitionNotAllowed(to_status)
    if step.needs_reason:
        _reason_given(comment)
    if step.guard:
        step.guard(request)

    previous, now = request.status, timezone.now()
    request.status, request.status_changed_at = to_status, now
    request.save(update_fields=["status", "status_changed_at", "updated_at"])
    event = RequestStatusEvent.objects.create(
        request=request,
        from_status=previous,
        to_status=to_status,
        changed_by=actor,
        changed_at=now,
        comment=comment.strip(),
    )
    notify_status_change(request, event)
    return request
