"""Business rules for dataset requests. Views and commands call these; they never change requests directly."""

from django.db import transaction

from apps.notifications.services import notify_status_change
from apps.requests_desk.models import DatasetRequest, RequestStatus, RequestStatusEvent


@transaction.atomic
def submit_request(client, *, task_name, episodes_requested, deadline, notes="") -> DatasetRequest:
    request = DatasetRequest.objects.create(
        client=client,
        task_name=task_name,
        episodes_requested=episodes_requested,
        deadline=deadline,
        notes=notes,
    )
    event = RequestStatusEvent.objects.create(
        request=request,
        from_status=None,
        to_status=RequestStatus.SUBMITTED,
        changed_by=client,
        changed_at=request.status_changed_at,
    )
    notify_status_change(request, event)
    return request
