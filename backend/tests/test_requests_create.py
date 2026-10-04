from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.core.dates import business_today
from apps.requests_desk.models import DatasetRequest, RequestStatus

REQUESTS = "/api/requests/"

pytestmark = pytest.mark.django_db


def payload(**overrides):
    data = {
        "task_name": "pick cup",
        "episodes_requested": 200,
        "deadline": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "notes": "Robot arm picking cups from a cluttered table.",
    }
    data.update(overrides)
    return data


def test_client_submits_a_request(api_as):
    client = api_as("client", organisation="Acme Robotics")

    response = client.post(REQUESTS, payload(), format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert body["task_name"] == "pick cup"
    assert body["episodes_requested"] == 200
    assert body["client"] == {
        "id": str(client.user.id),
        "full_name": client.user.full_name,
        "organisation": "Acme Robotics",
    }
    saved = DatasetRequest.objects.get(pk=body["id"])
    assert saved.client == client.user


def test_task_name_is_normalised_like_episode_task_names(api_as):
    response = api_as("client").post(REQUESTS, payload(task_name="  Pick   CUP "), format="json")

    assert response.json()["task_name"] == "pick cup"


def test_submission_is_recorded_in_the_status_history(api_as):
    client = api_as("client")

    request_id = client.post(REQUESTS, payload(), format="json").json()["id"]

    [event] = DatasetRequest.objects.get(pk=request_id).events.all()
    assert (event.from_status, event.to_status) == (None, RequestStatus.SUBMITTED)
    assert event.changed_by == client.user


def test_status_and_owner_cannot_be_chosen_by_the_client(api_as, make_user):
    other = make_user(email="other@example.com")
    client = api_as("client")

    body = client.post(REQUESTS, payload(status="accepted", client=str(other.id)), format="json").json()

    assert body["status"] == "submitted"
    assert body["client"]["id"] == str(client.user.id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("episodes_requested", 0),
        ("episodes_requested", -5),
        ("episodes_requested", 1_000_001),
        ("task_name", "   "),
        ("task_name", "x" * 121),
        ("deadline", (business_today() - timedelta(days=1)).isoformat()),
        ("notes", "x" * 2001),
    ],
)
def test_invalid_values_are_rejected_per_field(api_as, field, value):
    response = api_as("client").post(REQUESTS, payload(**{field: value}), format="json")

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_a_deadline_of_today_is_allowed(api_as):
    response = api_as("client").post(REQUESTS, payload(deadline=business_today().isoformat()), format="json")

    assert response.status_code == 201


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_only_clients_can_submit_requests(api_as, role):
    response = api_as(role).post(REQUESTS, payload(), format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_requires_authentication(api_client):
    assert api_client.post(REQUESTS, payload(), format="json").status_code == 401


class TestDatabaseConstraints:
    def test_episodes_requested_must_be_positive(self, make_user):
        with pytest.raises(IntegrityError):
            DatasetRequest.objects.create(
                client=make_user(), task_name="pick cup", episodes_requested=0, deadline=timezone.localdate()
            )

    def test_status_must_be_known(self, make_user):
        with pytest.raises(IntegrityError):
            DatasetRequest.objects.create(
                client=make_user(),
                task_name="pick cup",
                episodes_requested=1,
                deadline=timezone.localdate(),
                status="lost",
            )
