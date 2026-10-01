"""Assigning episodes to requests (PLAN.md §7.3).

- only ``good`` or ``usable`` episodes, and only episodes recorded for the request's task;
- an episode is active on at most one request (also enforced by a partial unique index);
- only while the request is ``in_progress``;
- a bulk assign is all-or-nothing.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions, status

from apps.catalog.models import ASSIGNABLE_QUALITIES, Episode
from apps.requests_desk.models import Assignment, DatasetRequest, RequestStatus

MAX_EPISODES_PER_CALL = 500


class RequestNotInProgress(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "request_not_in_progress"

    def __init__(self, current):
        super().__init__(f"Episodes can only be changed while the request is in progress (it is {current}).")


class EpisodesNotAssignable(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "episodes_not_assignable"

    def __init__(self, problems: dict[str, list[str]]):
        super().__init__("Some episodes can't be assigned to this request. Nothing was assigned.")
        self.details = problems


class EpisodesAlreadyAssigned(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "episodes_already_assigned"

    def __init__(self, holders: dict[str, str]):
        super().__init__("Some episodes are already assigned to a request. Nothing was assigned.")
        self.details = holders  # episode id -> id of the request holding it


def _locked_in_progress(request: DatasetRequest) -> DatasetRequest:
    # Locking the request means its status can't change (e.g. to delivered) while episodes are being changed.
    request = DatasetRequest.objects.select_for_update().get(pk=request.pk)
    if request.status != RequestStatus.IN_PROGRESS:
        raise RequestNotInProgress(request.status)
    return request


def _holders(episode_ids) -> dict[str, str]:
    active = Assignment.objects.filter(episode__episode_id__in=episode_ids, released_at__isnull=True)
    return {
        episode_id: str(request_id)
        for episode_id, request_id in active.values_list("episode__episode_id", "request_id")
    }


@transaction.atomic
def assign_episodes(request: DatasetRequest, episode_ids: list[str], *, actor) -> list[str]:
    """Assign every listed episode to the request, or none of them. Returns the assigned ids in order."""
    request = _locked_in_progress(request)
    wanted = list(dict.fromkeys(episode_id.strip().upper() for episode_id in episode_ids))
    episodes = {episode.episode_id: episode for episode in Episode.objects.filter(episode_id__in=wanted)}

    problems = {
        "unknown": [eid for eid in wanted if eid not in episodes],
        "bad_quality": [
            eid for eid in wanted if eid in episodes and episodes[eid].quality not in ASSIGNABLE_QUALITIES
        ],
        "task_mismatch": [
            eid for eid in wanted if eid in episodes and episodes[eid].task_name != request.task_name
        ],
    }
    problems = {reason: ids for reason, ids in problems.items() if ids}
    if problems:
        raise EpisodesNotAssignable(problems)

    holders = _holders(wanted)
    if holders:
        raise EpisodesAlreadyAssigned(holders)

    try:
        with transaction.atomic():
            Assignment.objects.bulk_create(
                [Assignment(request=request, episode=episodes[eid], assigned_by=actor) for eid in wanted]
            )
    except IntegrityError:
        # Another operator assigned one of these episodes after the check above; the database's partial
        # unique index refused it. Report it the same way as if the check had caught it.
        raise EpisodesAlreadyAssigned(_holders(wanted)) from None
    return wanted


@transaction.atomic
def unassign_episode(request: DatasetRequest, episode_id: str, *, actor) -> None:
    """Release one episode from the request. The assignment row is kept as history."""
    request = _locked_in_progress(request)
    released = Assignment.objects.filter(
        request=request, episode__episode_id=episode_id.strip().upper(), released_at__isnull=True
    ).update(released_at=timezone.now(), released_by=actor)
    if not released:
        raise exceptions.NotFound("That episode is not assigned to this request.")


def active_count(request: DatasetRequest) -> int:
    return request.assignments.filter(released_at__isnull=True).count()
