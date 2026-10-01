from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.models import Assignment
from apps.requests_desk.services import submit_request

EPISODES = "/api/episodes/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def robots():
    for robot_id in ("arm-01", "mobile-01"):
        Robot.objects.create(id=robot_id, kind=Robot.kind_from_id(robot_id))


def episode(episode_id, task="pick cup", quality=Quality.GOOD, robot="arm-01", day=1):
    return Episode.objects.create(
        episode_id=episode_id,
        robot_id=robot,
        task_name=task,
        recorded_at=datetime(2026, 8, day, 10, 0, tzinfo=UTC),
        duration_seconds=30,
        quality=quality,
    )


def ids(response):
    return [item["episode_id"] for item in response.json()["results"]]


@pytest.fixture
def catalogue():
    episode("EP-00001", task="pick cup", quality=Quality.GOOD, day=1)
    episode("EP-00002", task="pick cup", quality=Quality.BAD, day=2)
    episode("EP-00003", task="fold towel", quality=Quality.USABLE, robot="mobile-01", day=3)
    episode("EP-00004", task="pick cup", quality=Quality.USABLE, robot="mobile-01", day=4)


@pytest.fixture
def operator(api_as):
    return api_as("operator")


def test_lists_episodes_newest_first_with_their_details(operator, catalogue):
    response = operator.get(EPISODES)

    assert response.status_code == 200
    assert ids(response) == ["EP-00004", "EP-00003", "EP-00002", "EP-00001"]
    first = response.json()["results"][0]
    assert first == {
        "id": first["id"],
        "episode_id": "EP-00004",
        "robot_id": "mobile-01",
        "task_name": "pick cup",
        "recorded_at": "2026-08-04T10:00:00Z",
        "duration_seconds": 30,
        "operator_name": "",
        "quality": "usable",
        "assigned_request": None,
    }


class TestFilters:
    def test_by_task_name_normalised_like_stored_names(self, operator, catalogue):
        assert ids(operator.get(EPISODES, {"task_name": "  Pick CUP "})) == [
            "EP-00004",
            "EP-00002",
            "EP-00001",
        ]

    def test_by_quality(self, operator, catalogue):
        assert ids(operator.get(EPISODES, {"quality": "usable"})) == ["EP-00004", "EP-00003"]

    def test_by_several_qualities(self, operator, catalogue):
        # What the assignment screen asks for: everything that may be delivered.
        response = operator.get(EPISODES, {"quality": ["good", "usable"]})

        assert ids(response) == ["EP-00004", "EP-00003", "EP-00001"]

    def test_by_robot(self, operator, catalogue):
        assert ids(operator.get(EPISODES, {"robot_id": "mobile-01"})) == ["EP-00004", "EP-00003"]

    def test_filters_combine(self, operator, catalogue):
        response = operator.get(
            EPISODES, {"task_name": "pick cup", "quality": "usable", "robot_id": "mobile-01"}
        )

        assert ids(response) == ["EP-00004"]

    @pytest.mark.parametrize(
        "params", [{"quality": "excellent"}, {"available": "maybe"}, {"ordering": "operator_name"}]
    )
    def test_invalid_filters_are_rejected(self, operator, params):
        response = operator.get(EPISODES, params)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid"


class TestAvailability:
    @pytest.fixture
    def assigned(self, catalogue, make_user, operator):
        client = make_user(email="client@example.com")
        request = submit_request(
            client,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=7),
        )
        Assignment.objects.create(
            request=request, episode=Episode.objects.get(episode_id="EP-00001"), assigned_by=operator.user
        )
        released = Assignment.objects.create(
            request=request,
            episode=Episode.objects.get(episode_id="EP-00004"),
            assigned_by=operator.user,
            released_at=timezone.now(),
            released_by=operator.user,
        )
        return request, released

    def test_available_means_not_actively_assigned(self, operator, assigned):
        assert ids(operator.get(EPISODES, {"available": "true"})) == ["EP-00004", "EP-00003", "EP-00002"]

    def test_unavailable_lists_only_actively_assigned(self, operator, assigned):
        assert ids(operator.get(EPISODES, {"available": "false"})) == ["EP-00001"]

    def test_shows_which_request_holds_an_episode(self, operator, assigned):
        request, _ = assigned
        results = {item["episode_id"]: item for item in operator.get(EPISODES).json()["results"]}

        assert results["EP-00001"]["assigned_request"] == str(request.id)
        assert results["EP-00004"]["assigned_request"] is None  # released


def test_can_be_ordered_by_recording_time_ascending(operator, catalogue):
    assert ids(operator.get(EPISODES, {"ordering": "recorded_at"})) == [
        "EP-00001",
        "EP-00002",
        "EP-00003",
        "EP-00004",
    ]


def test_results_are_paginated(operator):
    for n in range(30):
        episode(f"EP-{n:05d}")

    body = operator.get(EPISODES).json()

    assert body["count"] == 30
    assert len(body["results"]) == 25


@pytest.mark.parametrize("role", ["admin"])
def test_admins_can_browse(api_as, catalogue, role):
    assert api_as(role).get(EPISODES).status_code == 200


def test_clients_cannot_browse_the_catalogue(api_as, catalogue):
    assert api_as("client").get(EPISODES).status_code == 403


def test_listing_uses_a_fixed_number_of_queries(operator, catalogue, django_assert_max_num_queries):
    for n in range(20):
        episode(f"EP-1{n:04d}")

    with django_assert_max_num_queries(2):  # count, then one page with the assignment looked up in SQL
        operator.get(EPISODES)
