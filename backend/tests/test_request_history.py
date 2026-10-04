from datetime import timedelta

import pytest
from django.utils import timezone

from apps.requests_desk.models import DatasetRequest, RequestStatus
from apps.requests_desk.services import submit_request
from apps.requests_desk.workflow import transition

pytestmark = pytest.mark.django_db


def events_url(request):
    return f"/api/requests/{request.id}/events/"


@pytest.fixture
def owner(api_as):
    return api_as("client", full_name="Acme Robotics")


@pytest.fixture
def operator(api_as):
    return api_as("operator", full_name="Olu Operator")


@pytest.fixture
def rejected_request(owner, operator):
    """submitted -> in_progress -> delivered -> rejected through the real workflow.

    Delivery is set directly to skip assigning episodes, so there is no delivered event.
    """
    request = submit_request(
        owner.user,
        task_name="pick cup",
        episodes_requested=1,
        deadline=timezone.localdate() + timedelta(days=7),
    )
    transition(request, to_status=RequestStatus.IN_PROGRESS, actor=operator.user)
    DatasetRequest.objects.filter(pk=request.pk).update(status=RequestStatus.DELIVERED)  # skip assigning
    transition(request, to_status=RequestStatus.REJECTED, actor=owner.user, comment="Wrong cup.")
    return request


def test_lists_every_change_in_order_with_who_and_why(owner, rejected_request):
    response = owner.get(events_url(rejected_request))

    assert response.status_code == 200
    events = response.json()["results"]
    assert [(e["from_status"], e["to_status"]) for e in events] == [
        (None, "submitted"),
        ("submitted", "in_progress"),
        ("delivered", "rejected"),
    ]
    assert events[0]["changed_by"] == {"full_name": "Acme Robotics", "role": "client"}
    assert events[1]["changed_by"] == {"full_name": "Olu Operator", "role": "operator"}
    assert events[2]["comment"] == "Wrong cup."
    assert all(e["changed_at"] for e in events)


def test_staff_see_the_history_of_any_request(api_as, rejected_request):
    assert api_as("admin").get(events_url(rejected_request)).status_code == 200


def test_another_client_cannot_see_the_history(api_as, rejected_request):
    assert api_as("client").get(events_url(rejected_request)).status_code == 404


@pytest.mark.parametrize("method", ["put", "patch", "delete", "post"])
def test_history_is_read_only(owner, rejected_request, method):
    response = getattr(owner, method)(events_url(rejected_request), {}, format="json")

    assert response.status_code == 405


def test_staff_emails_are_not_exposed_to_clients(owner, rejected_request):
    body = owner.get(events_url(rejected_request)).content.decode()

    assert "@example.com" not in body


def test_long_histories_are_paginated(owner, operator, rejected_request):
    # A request reworked many times keeps growing its history: the response must stay bounded.
    for _ in range(15):
        DatasetRequest.objects.filter(pk=rejected_request.pk).update(status=RequestStatus.DELIVERED)
        transition(rejected_request, to_status=RequestStatus.REJECTED, actor=owner.user, comment="Again.")

    first = owner.get(events_url(rejected_request), {"page_size": 10}).json()
    second = owner.get(first["next"]).json()

    assert first["count"] == 18
    assert len(first["results"]) == 10
    assert first["results"][0]["to_status"] == "submitted"  # still oldest first
    assert len(second["results"]) == 8
    assert second["next"] is None


def test_uses_a_fixed_number_of_queries(owner, rejected_request, django_assert_max_num_queries):
    # The request (scope check), the event count, and one page of events with their authors joined.
    with django_assert_max_num_queries(3):
        owner.get(events_url(rejected_request))
