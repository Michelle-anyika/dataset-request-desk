"""Analytics are computed once and shared, invalidated when the underlying data changes.

Every staff member sees the same numbers, so a cached result is safe to share; correctness comes from
invalidation (a data version bumped on every change), not from a short lifetime.
"""

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.analytics import cache as analytics_cache
from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.services import submit_request

ANALYTICS = "/api/analytics/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def robot():
    return Robot.objects.create(id="arm-01", kind="arm")


@pytest.fixture
def operator(api_as):
    return api_as("operator")


def get(client):
    return client.get(ANALYTICS, {"from": "2026-08-01", "to": "2026-08-31"}).json()


def episode(n):
    Episode.objects.create(
        episode_id=f"EP-{n:05d}",
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime(2026, 8, 5, 10, tzinfo=UTC),
        duration_seconds=30,
        quality=Quality.GOOD,
    )


def test_a_repeated_query_is_served_from_the_cache(operator, django_assert_max_num_queries):
    episode(1)
    first = get(operator)

    with django_assert_max_num_queries(2):  # data version + cached result; none of the 4 aggregations
        second = get(operator)

    assert second == first


def test_different_ranges_are_cached_separately(operator):
    episode(1)
    august = get(operator)

    september = operator.get(ANALYTICS, {"from": "2026-09-01", "to": "2026-09-30"}).json()

    assert august["episodes_per_day"] != september["episodes_per_day"]


def test_a_new_request_invalidates_the_numbers(operator, make_user, django_capture_on_commit_callbacks):
    today = timezone.localdate().isoformat()
    params = {"from": today, "to": today}
    assert operator.get(ANALYTICS, params).json()["requests"]["by_status"]["submitted"] == 0  # now cached
    client = make_user(email="client@example.com")

    with django_capture_on_commit_callbacks(execute=True):
        submit_request(
            client,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=9),
        )

    # The same query as before: only invalidation can make it change.
    assert operator.get(ANALYTICS, params).json()["requests"]["by_status"]["submitted"] == 1


def test_an_import_invalidates_the_numbers(operator, make_user, tmp_path):
    before = get(operator)
    make_user(email="ops@example.com", role="operator")
    export = tmp_path / "export.csv"
    export.write_text(
        "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        "EP-00001,arm-01,pick cup,2026-08-05T10:00:00,30,Aline,good\n"
    )

    call_command("import_episodes", str(export), "--as", "ops@example.com", stdout=StringIO())

    after = get(operator)
    assert before["episodes_per_day"] == []
    assert after["episodes_per_day"] == [{"date": "2026-08-05", "robot_id": "arm-01", "episodes": 1}]


def test_concurrent_misses_compute_once(monkeypatch):
    """Stampede protection: while one worker computes, others wait for its result instead of recomputing."""
    computed = []

    def compute():
        computed.append(1)
        return {"answer": 42}

    lock_key = analytics_cache.lock_key("range")
    # Another worker already holds the lock and publishes its result while we wait.
    analytics_cache.cache.add(lock_key, "other-worker", 30)

    def result_arrives(seconds):
        analytics_cache.cache.set(analytics_cache.result_key("range"), {"answer": 42}, 60)

    monkeypatch.setattr(analytics_cache.time, "sleep", result_arrives)

    assert analytics_cache.get_or_compute("range", compute) == {"answer": 42}
    assert computed == []
