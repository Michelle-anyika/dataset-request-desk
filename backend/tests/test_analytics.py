"""Analytics against a small fixed dataset with exact expected numbers."""

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.models import DatasetRequest, RequestStatus, RequestStatusEvent

ANALYTICS = "/api/analytics/"
S = RequestStatus

pytestmark = pytest.mark.django_db


def at(day, hour=10, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


@pytest.fixture(autouse=True)
def robots():
    for robot_id in ("arm-01", "mobile-01"):
        Robot.objects.create(id=robot_id, kind=Robot.kind_from_id(robot_id))


@pytest.fixture
def operator(api_as):
    return api_as("operator")


def episode(n, recorded_at, robot="arm-01", task="pick cup", quality=Quality.GOOD):
    Episode.objects.create(
        episode_id=f"EP-{n:05d}",
        robot_id=robot,
        task_name=task,
        recorded_at=recorded_at,
        duration_seconds=30,
        quality=quality,
    )


def get(client, start="2026-08-01", end="2026-08-31"):
    return client.get(ANALYTICS, {"from": start, "to": end})


class TestEpisodesPerDayPerRobot:
    def test_counts_by_utc_day_and_robot(self, operator):
        episode(1, at(1, 9))
        episode(2, at(1, 23, 30))  # still 1 August in UTC
        episode(3, at(2, 0, 10))
        episode(4, at(1, 12), robot="mobile-01")
        episode(5, datetime(2026, 7, 31, 23, 59, tzinfo=UTC))  # before the range
        episode(6, datetime(2026, 9, 1, 0, 0, tzinfo=UTC))  # after the range

        body = get(operator).json()

        assert body["episodes_per_day"] == [
            {"date": "2026-08-01", "robot_id": "arm-01", "episodes": 2},
            {"date": "2026-08-01", "robot_id": "mobile-01", "episodes": 1},
            {"date": "2026-08-02", "robot_id": "arm-01", "episodes": 1},
        ]

    def test_the_end_date_is_inclusive(self, operator):
        episode(1, at(31, 23, 59))

        assert get(operator).json()["episodes_per_day"] == [
            {"date": "2026-08-31", "robot_id": "arm-01", "episodes": 1}
        ]


class TestTopTasksByGoodEpisodes:
    def test_top_five_tasks_ranked_by_good_episodes_only(self, operator):
        counts = {
            "pick cup": 4,
            "fold towel": 3,
            "open drawer": 2,
            "pour water": 2,
            "wipe table": 1,
            "stack blocks": 1,
        }
        n = 0
        for task, good in counts.items():
            for _ in range(good):
                n += 1
                episode(n, at(5), task=task)
        for _ in range(5):  # bad and usable episodes don't count
            n += 1
            episode(n, at(5), task="stack blocks", quality=Quality.BAD)
        n += 1
        episode(n, at(5), task="stack blocks", quality=Quality.USABLE)

        top = get(operator).json()["top_tasks_by_good_episodes"]

        assert top == [
            {"task_name": "pick cup", "good_episodes": 4},
            {"task_name": "fold towel", "good_episodes": 3},
            {"task_name": "open drawer", "good_episodes": 2},  # ties broken alphabetically
            {"task_name": "pour water", "good_episodes": 2},
            {"task_name": "stack blocks", "good_episodes": 1},
        ]


class TestRequestFulfilment:
    @pytest.fixture
    def client_user(self, make_user):
        return make_user(email="client@example.com")

    def request(self, client_user, created_at, status=S.SUBMITTED):
        request = DatasetRequest.objects.create(
            client=client_user,
            task_name="pick cup",
            episodes_requested=1,
            deadline=date(2026, 12, 1),
            status=status,
        )
        DatasetRequest.objects.filter(pk=request.pk).update(created_at=created_at)
        RequestStatusEvent.objects.create(
            request=request, to_status=S.SUBMITTED, changed_by=client_user, changed_at=created_at
        )
        return request

    def delivered(self, request, after_hours, by):
        RequestStatusEvent.objects.create(
            request=request,
            from_status=S.IN_PROGRESS,
            to_status=S.DELIVERED,
            changed_by=by,
            changed_at=DatasetRequest.objects.get(pk=request.pk).created_at + timedelta(hours=after_hours),
        )

    def test_counts_requests_submitted_in_the_range_by_status(self, operator, client_user):
        self.request(client_user, at(3), S.SUBMITTED)
        self.request(client_user, at(4), S.IN_PROGRESS)
        self.request(client_user, at(5), S.IN_PROGRESS)
        self.request(client_user, at(6), S.ACCEPTED)
        self.request(client_user, datetime(2026, 7, 1, tzinfo=UTC), S.REJECTED)  # outside the range

        by_status = get(operator).json()["requests"]["by_status"]

        assert by_status == {"submitted": 1, "in_progress": 2, "delivered": 0, "accepted": 1, "rejected": 0}

    def test_median_time_from_submission_to_first_delivery(self, operator, client_user):
        for hours in (2, 4, 10):
            self.delivered(self.request(client_user, at(3), S.DELIVERED), hours, operator.user)
        self.request(client_user, at(3), S.IN_PROGRESS)  # not delivered yet: not part of the median

        requests = get(operator).json()["requests"]

        assert requests["median_hours_to_delivery"] == 4.0
        assert requests["delivered_count"] == 3

    def test_median_of_an_even_count_interpolates(self, operator, client_user):
        for hours in (2, 4, 6, 10):
            self.delivered(self.request(client_user, at(3), S.DELIVERED), hours, operator.user)

        assert get(operator).json()["requests"]["median_hours_to_delivery"] == 5.0

    def test_rework_does_not_reset_the_clock(self, operator, client_user):
        # Decision #6: the first delivery counts, so a rejected and re-delivered request isn't flattered.
        request = self.request(client_user, at(3), S.DELIVERED)
        self.delivered(request, 2, operator.user)
        self.delivered(request, 30, operator.user)

        assert get(operator).json()["requests"]["median_hours_to_delivery"] == 2.0

    def test_no_deliveries_gives_no_median(self, operator, client_user):
        self.request(client_user, at(3))

        requests = get(operator).json()["requests"]

        assert requests["median_hours_to_delivery"] is None
        assert requests["delivered_count"] == 0


class TestRange:
    def test_defaults_to_the_last_30_days(self, operator):
        body = operator.get(ANALYTICS).json()

        start, end = date.fromisoformat(body["range"]["from"]), date.fromisoformat(body["range"]["to"])
        assert (end - start).days == 29

    @pytest.mark.parametrize(
        "params",
        [
            {"from": "2026-08-31", "to": "2026-08-01"},  # reversed
            {"from": "yesterday", "to": "2026-08-01"},
            {"from": "2025-01-01", "to": "2026-08-01"},  # longer than a year: bounded cost
        ],
    )
    def test_invalid_ranges_are_rejected(self, operator, params):
        response = operator.get(ANALYTICS, params)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid"


def test_clients_cannot_see_analytics(api_as):
    assert api_as("client").get(ANALYTICS).status_code == 403


def test_everything_is_computed_in_a_fixed_number_of_queries(operator, django_assert_max_num_queries):
    for n in range(50):
        episode(n, at(1 + n % 28), robot="arm-01" if n % 2 else "mobile-01")

    with django_assert_max_num_queries(4):  # per day, top tasks, status counts, median
        get(operator)
