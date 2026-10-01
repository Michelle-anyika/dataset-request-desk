from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.models import Assignment, DatasetRequest, RequestStatus
from apps.requests_desk.services import submit_request

S = RequestStatus

pytestmark = pytest.mark.django_db


def assignments_url(request, episode_id=None):
    url = f"/api/requests/{request.id}/assignments/"
    return f"{url}{episode_id}/" if episode_id else url


@pytest.fixture(autouse=True)
def robot():
    return Robot.objects.create(id="arm-01", kind="arm")


@pytest.fixture
def owner(api_as):
    return api_as("client", organisation="Acme Robotics")


@pytest.fixture
def operator(api_as):
    return api_as("operator")


@pytest.fixture
def make_request(owner):
    def make(status=S.IN_PROGRESS, episodes_requested=2, task_name="pick cup"):
        request = submit_request(
            owner.user,
            task_name=task_name,
            episodes_requested=episodes_requested,
            deadline=timezone.localdate() + timedelta(days=14),
        )
        DatasetRequest.objects.filter(pk=request.pk).update(status=status)  # test setup only
        request.refresh_from_db()
        return request

    return make


def episode(episode_id, quality=Quality.GOOD, task="pick cup"):
    return Episode.objects.create(
        episode_id=episode_id,
        robot_id="arm-01",
        task_name=task,
        recorded_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        duration_seconds=30,
        quality=quality,
    )


def assign(client, request, *episode_ids):
    return client.post(assignments_url(request), {"episode_ids": list(episode_ids)}, format="json")


def active_ids(request):
    return sorted(
        request.assignments.filter(released_at__isnull=True).values_list("episode__episode_id", flat=True)
    )


class TestAssigning:
    @pytest.mark.parametrize("role", ["operator", "admin"])
    def test_staff_assign_good_and_usable_episodes(self, api_as, make_request, role):
        staff = api_as(role)
        request = make_request()
        episode("EP-00001", Quality.GOOD)
        episode("EP-00002", Quality.USABLE)

        response = assign(staff, request, "EP-00001", "EP-00002")

        assert response.status_code == 201
        assert response.json() == {
            "assigned": ["EP-00001", "EP-00002"],
            "assigned_count": 2,
            "episodes_requested": 2,
        }
        assert active_ids(request) == ["EP-00001", "EP-00002"]
        assert set(request.assignments.values_list("assigned_by", flat=True)) == {staff.user.pk}

    def test_ids_are_matched_case_insensitively_and_deduplicated(self, operator, make_request):
        request = make_request()
        episode("EP-00001")

        response = assign(operator, request, "ep-00001", "EP-00001")

        assert response.status_code == 201
        assert response.json()["assigned"] == ["EP-00001"]


class TestAllOrNothing:
    def test_a_bad_episode_is_refused_and_nothing_is_assigned(self, operator, make_request):
        request = make_request()
        episode("EP-00001", Quality.GOOD)
        episode("EP-00002", Quality.BAD)

        response = assign(operator, request, "EP-00001", "EP-00002")

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "episodes_not_assignable"
        assert error["details"] == {"bad_quality": ["EP-00002"]}
        assert active_ids(request) == []

    def test_unknown_episodes_are_reported(self, operator, make_request):
        response = assign(operator, make_request(), "EP-99999")

        assert response.status_code == 400
        assert response.json()["error"]["details"] == {"unknown": ["EP-99999"]}

    def test_episodes_for_another_task_are_refused(self, operator, make_request):
        request = make_request(task_name="pick cup")
        episode("EP-00001", task="fold towel")

        response = assign(operator, request, "EP-00001")

        assert response.status_code == 400
        assert response.json()["error"]["details"] == {"task_mismatch": ["EP-00001"]}

    def test_an_episode_held_by_another_request_is_refused(self, operator, make_request):
        first, second = make_request(), make_request()
        episode("EP-00001")
        episode("EP-00002")
        assign(operator, first, "EP-00001")

        response = assign(operator, second, "EP-00002", "EP-00001")

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "episodes_already_assigned"
        assert error["details"] == {"EP-00001": str(first.id)}
        assert active_ids(second) == []

    def test_an_episode_already_on_this_request_is_refused(self, operator, make_request):
        request = make_request()
        episode("EP-00001")
        assign(operator, request, "EP-00001")

        response = assign(operator, request, "EP-00001")

        assert response.status_code == 409
        assert response.json()["error"]["details"] == {"EP-00001": str(request.id)}


class TestOnlyWhileInProgress:
    @pytest.mark.parametrize("status", [S.SUBMITTED, S.DELIVERED, S.ACCEPTED, S.REJECTED])
    def test_assigning_is_refused_outside_in_progress(self, operator, make_request, status):
        request = make_request(status=status)
        episode("EP-00001")

        response = assign(operator, request, "EP-00001")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "request_not_in_progress"

    @pytest.mark.parametrize("status", [S.DELIVERED, S.ACCEPTED])
    def test_unassigning_is_refused_outside_in_progress(self, operator, make_request, status):
        request = make_request()
        episode("EP-00001")
        assign(operator, request, "EP-00001")
        DatasetRequest.objects.filter(pk=request.pk).update(status=status)

        response = operator.delete(assignments_url(request, "EP-00001"))

        assert response.status_code == 409
        assert active_ids(request) == ["EP-00001"]


class TestValidation:
    @pytest.mark.parametrize(
        "payload", [{}, {"episode_ids": []}, {"episode_ids": ["EP-1"] * 501}, {"episode_ids": "EP-1"}]
    )
    def test_the_list_of_ids_is_required_and_bounded(self, operator, make_request, payload):
        response = operator.post(assignments_url(make_request()), payload, format="json")

        assert response.status_code == 400
        assert "episode_ids" in response.json()["error"]["details"]


class TestUnassigning:
    def test_releases_the_episode_and_keeps_the_history(self, operator, make_request):
        request, other = make_request(), make_request()
        episode("EP-00001")
        assign(operator, request, "EP-00001")

        response = operator.delete(assignments_url(request, "ep-00001"))

        assert response.status_code == 204
        released = Assignment.objects.get(request=request)
        assert released.released_at is not None
        assert released.released_by == operator.user
        assert assign(operator, other, "EP-00001").status_code == 201  # available again

    def test_an_episode_not_on_the_request_is_not_found(self, operator, make_request):
        episode("EP-00001")

        response = operator.delete(assignments_url(make_request(), "EP-00001"))

        assert response.status_code == 404


class TestWhoMayDoWhat:
    def test_clients_cannot_assign_or_unassign(self, owner, operator, make_request):
        request = make_request()
        episode("EP-00001")
        episode("EP-00002")
        assign(operator, request, "EP-00001")

        assert assign(owner, request, "EP-00002").status_code == 403
        assert owner.delete(assignments_url(request, "EP-00001")).status_code == 403

    def test_the_owner_sees_what_is_assigned_to_their_request(self, owner, operator, make_request):
        request = make_request()
        episode("EP-00001")
        episode("EP-00002")
        assign(operator, request, "EP-00001", "EP-00002")
        operator.delete(assignments_url(request, "EP-00002"))

        response = owner.get(assignments_url(request))

        assert response.status_code == 200
        [item] = response.json()["results"]
        assert item["episode"]["episode_id"] == "EP-00001"
        assert item["episode"]["quality"] == "good"
        assert "released_at" not in item  # clients see what they get, not internal history

    def test_staff_can_include_released_assignments(self, operator, make_request):
        request = make_request()
        episode("EP-00001")
        assign(operator, request, "EP-00001")
        operator.delete(assignments_url(request, "EP-00001"))

        results = operator.get(assignments_url(request), {"history": "true"}).json()["results"]

        assert [(r["episode"]["episode_id"], r["released_at"] is not None) for r in results] == [
            ("EP-00001", True)
        ]

    def test_another_client_cannot_see_the_assignments(self, api_as, make_request):
        assert api_as("client").get(assignments_url(make_request())).status_code == 404


class TestProgressAndDelivery:
    def test_the_request_shows_how_many_episodes_are_assigned(self, owner, operator, make_request):
        request = make_request(episodes_requested=3)
        episode("EP-00001")
        assign(operator, request, "EP-00001")

        detail = owner.get(f"/api/requests/{request.id}/").json()

        assert (detail["assigned_count"], detail["episodes_requested"]) == (1, 3)

    def test_assigning_enough_episodes_unlocks_delivery(self, operator, make_request):
        request = make_request(episodes_requested=2)
        episode("EP-00001")
        episode("EP-00002")
        transitions = f"/api/requests/{request.id}/transitions/"

        assert operator.post(transitions, {"to_status": "delivered"}, format="json").status_code == 409
        assign(operator, request, "EP-00001", "EP-00002")
        assert operator.post(transitions, {"to_status": "delivered"}, format="json").status_code == 200


def test_listing_assignments_uses_a_fixed_number_of_queries(
    operator, make_request, django_assert_max_num_queries
):
    request = make_request(episodes_requested=20)
    for n in range(20):
        episode(f"EP-{n:05d}")
    assign(operator, request, *[f"EP-{n:05d}" for n in range(20)])

    with django_assert_max_num_queries(3):  # the request (scope), count, page with episodes joined
        operator.get(assignments_url(request))


def test_a_race_lost_to_another_operator_is_reported_not_crashed(operator, make_request, monkeypatch):
    """Two operators assign one episode at once: both pass the pre-check, the database refuses one."""
    from apps.requests_desk import assignments

    first, second = make_request(), make_request()
    episode("EP-00001")
    assign(operator, first, "EP-00001")
    real_holders, calls = assignments._holders, []

    def misses_the_first_time(episode_ids):
        calls.append(episode_ids)
        return {} if len(calls) == 1 else real_holders(episode_ids)

    monkeypatch.setattr(assignments, "_holders", misses_the_first_time)

    response = assign(operator, second, "EP-00001")

    assert response.status_code == 409  # the partial unique index refused it, and it's reported cleanly
    assert response.json()["error"]["details"] == {"EP-00001": str(first.id)}
    assert active_ids(second) == []
