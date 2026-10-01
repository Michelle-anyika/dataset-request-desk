from datetime import timedelta
from itertools import product

import pytest
from django.utils import timezone

from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.models import Assignment, DatasetRequest, RequestStatus
from apps.requests_desk.services import submit_request

S = RequestStatus
ALLOWED = {
    (S.SUBMITTED, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.DELIVERED),
    (S.DELIVERED, S.ACCEPTED),
    (S.DELIVERED, S.REJECTED),
    (S.REJECTED, S.IN_PROGRESS),
}
NOT_ALLOWED = sorted(set(product(S.values, S.values)) - ALLOWED)

pytestmark = pytest.mark.django_db


def transitions_url(request):
    return f"/api/requests/{request.id}/transitions/"


@pytest.fixture
def owner(api_as):
    return api_as("client", organisation="Acme Robotics")


@pytest.fixture
def operator(api_as):
    return api_as("operator")


@pytest.fixture
def make_request(owner):
    def make(status=S.SUBMITTED, episodes_requested=2):
        request = submit_request(
            owner.user,
            task_name="pick cup",
            episodes_requested=episodes_requested,
            deadline=timezone.localdate() + timedelta(days=14),
        )
        DatasetRequest.objects.filter(pk=request.pk).update(status=status)  # test setup only
        request.refresh_from_db()
        return request

    return make


@pytest.fixture
def assign(operator):
    robot = Robot.objects.create(id="arm-01", kind="arm")
    counter = iter(range(1, 10_000))

    def assign_episodes(request, count, released=False):
        for _ in range(count):
            episode = Episode.objects.create(
                episode_id=f"EP-{next(counter):05d}",
                robot=robot,
                task_name="pick cup",
                recorded_at=timezone.now(),
                duration_seconds=30,
                quality=Quality.GOOD,
            )
            Assignment.objects.create(
                request=request,
                episode=episode,
                assigned_by=operator.user,
                released_at=timezone.now() if released else None,
                released_by=operator.user if released else None,
            )

    return assign_episodes


def move(client, request, to_status, comment=None):
    data = {"to_status": to_status}
    if comment is not None:
        data["comment"] = comment
    return client.post(transitions_url(request), data, format="json")


@pytest.mark.parametrize("role", ["operator", "admin"])
class TestOperatorSteps:
    def test_starts_work_on_a_submitted_request(self, api_as, make_request, role):
        staff = api_as(role)
        request = make_request(S.SUBMITTED)

        response = move(staff, request, "in_progress")

        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"
        request.refresh_from_db()
        assert request.status == S.IN_PROGRESS
        event = request.events.last()
        assert (event.from_status, event.to_status, event.changed_by) == (
            S.SUBMITTED,
            S.IN_PROGRESS,
            staff.user,
        )
        assert request.status_changed_at == event.changed_at

    def test_reworks_a_rejected_request(self, api_as, make_request, role):
        request = make_request(S.REJECTED)

        assert move(api_as(role), request, "in_progress").status_code == 200

    def test_delivers_once_enough_episodes_are_assigned(self, api_as, make_request, assign, role):
        request = make_request(S.IN_PROGRESS, episodes_requested=2)
        assign(request, 2)

        response = move(api_as(role), request, "delivered")

        assert response.status_code == 200
        assert response.json()["status"] == "delivered"


class TestDeliveryNeedsEnoughEpisodes:
    def test_is_refused_with_too_few_assigned(self, operator, make_request, assign):
        request = make_request(S.IN_PROGRESS, episodes_requested=3)
        assign(request, 2)

        response = move(operator, request, "delivered")

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "not_enough_episodes"
        assert error["details"] == {"assigned": 2, "requested": 3}
        request.refresh_from_db()
        assert request.status == S.IN_PROGRESS

    def test_released_assignments_do_not_count(self, operator, make_request, assign):
        request = make_request(S.IN_PROGRESS, episodes_requested=2)
        assign(request, 1)
        assign(request, 3, released=True)

        assert move(operator, request, "delivered").status_code == 409


class TestClientSteps:
    def test_owner_accepts_a_delivery(self, owner, make_request):
        request = make_request(S.DELIVERED)

        response = move(owner, request, "accepted")

        assert response.status_code == 200
        assert request.events.last().changed_by == owner.user

    def test_owner_rejects_with_a_reason(self, owner, make_request):
        request = make_request(S.DELIVERED)

        response = move(owner, request, "rejected", "Half the clips show the wrong cup.")

        assert response.status_code == 200
        assert request.events.last().comment == "Half the clips show the wrong cup."

    @pytest.mark.parametrize("comment", [None, "", "    "])
    def test_rejecting_requires_a_reason(self, owner, make_request, comment):
        request = make_request(S.DELIVERED)

        response = move(owner, request, "rejected", comment)

        assert response.status_code == 400
        assert "comment" in response.json()["error"]["details"]
        request.refresh_from_db()
        assert request.status == S.DELIVERED

    def test_another_client_cannot_even_find_the_request(self, api_as, make_request):
        request = make_request(S.DELIVERED)

        response = move(api_as("client"), request, "accepted")

        assert response.status_code == 404


class TestRoleOwnsTheStep:
    @pytest.mark.parametrize(("start", "target"), [(S.SUBMITTED, S.IN_PROGRESS), (S.REJECTED, S.IN_PROGRESS)])
    def test_a_client_cannot_perform_operator_steps(self, owner, make_request, start, target):
        response = move(owner, make_request(start), target)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "transition_not_allowed"

    def test_a_client_cannot_deliver(self, owner, make_request, assign):
        request = make_request(S.IN_PROGRESS, episodes_requested=1)
        assign(request, 1)

        assert move(owner, request, "delivered").status_code == 403

    @pytest.mark.parametrize("role", ["operator", "admin"])
    @pytest.mark.parametrize("target", ["accepted", "rejected"])
    def test_staff_cannot_accept_or_reject_for_the_client(self, api_as, make_request, role, target):
        response = move(api_as(role), make_request(S.DELIVERED), target, "on behalf of the client")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "transition_not_allowed"


@pytest.mark.parametrize(("start", "target"), NOT_ALLOWED)
def test_every_other_transition_is_refused(operator, make_request, start, target):
    request = make_request(start)

    response = move(operator, request, target, "reason")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    request.refresh_from_db()
    assert request.status == start
    assert request.events.count() == 1  # only the submission


def test_an_unknown_status_is_a_validation_error(operator, make_request):
    response = move(operator, make_request(), "lost")

    assert response.status_code == 400
    assert "to_status" in response.json()["error"]["details"]


def test_the_full_lifecycle_is_recorded_in_order(owner, operator, make_request, assign):
    request = make_request(S.SUBMITTED, episodes_requested=1)
    move(operator, request, "in_progress")
    assign(request, 1)
    move(operator, request, "delivered")
    move(owner, request, "rejected", "Wrong lighting.")
    move(operator, request, "in_progress")
    move(operator, request, "delivered")
    move(owner, request, "accepted")

    history = [(e.from_status, e.to_status) for e in request.events.all()]

    assert history == [
        (None, "submitted"),
        ("submitted", "in_progress"),
        ("in_progress", "delivered"),
        ("delivered", "rejected"),
        ("rejected", "in_progress"),
        ("in_progress", "delivered"),
        ("delivered", "accepted"),
    ]
