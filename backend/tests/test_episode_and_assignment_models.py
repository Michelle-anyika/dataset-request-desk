from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.catalog.models import Episode, Quality, Robot
from apps.requests_desk.models import Assignment
from apps.requests_desk.services import submit_request

pytestmark = pytest.mark.django_db


@pytest.fixture
def robot():
    return Robot.objects.create(id="arm-01", kind="arm")


@pytest.fixture
def make_episode(robot):
    def make(episode_id="EP-00001", quality=Quality.GOOD, **fields):
        fields.setdefault("task_name", "pick cup")
        fields.setdefault("recorded_at", timezone.now())
        fields.setdefault("duration_seconds", 30)
        return Episode.objects.create(episode_id=episode_id, robot=robot, quality=quality, **fields)

    return make


@pytest.fixture
def make_request(make_user):
    client = make_user(email="client@example.com")

    def make():
        return submit_request(
            client,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=7),
        )

    return make


def assign(request, episode, by):
    return Assignment.objects.create(request=request, episode=episode, assigned_by=by)


class TestEpisodeConstraints:
    def test_episode_ids_are_unique(self, make_episode):
        make_episode("EP-00001")

        with pytest.raises(IntegrityError):
            make_episode("EP-00001")

    @pytest.mark.parametrize("duration", [0, -5])
    def test_duration_must_be_positive(self, make_episode, duration):
        with pytest.raises(IntegrityError):
            make_episode(duration_seconds=duration)

    def test_quality_must_be_known(self, make_episode):
        with pytest.raises(IntegrityError):
            make_episode(quality="excellent")

    def test_robot_must_exist(self):
        # Django's Postgres foreign keys are DEFERRABLE: checked at commit. Check now, as a commit would.
        with pytest.raises(IntegrityError), transaction.atomic():
            Episode.objects.create(
                episode_id="EP-9",
                robot_id="arm-99",
                task_name="x",
                recorded_at=timezone.now(),
                duration_seconds=1,
                quality=Quality.GOOD,
            )
            connection.check_constraints(table_names=["episodes"])


class TestOneActiveRequestPerEpisode:
    """Enforced by a partial unique index, so it holds even when two operators assign at the same moment."""

    def test_an_episode_cannot_be_active_on_two_requests(self, make_episode, make_request, make_user):
        operator = make_user(email="ops@example.com", role="operator")
        episode = make_episode()
        assign(make_request(), episode, operator)

        with pytest.raises(IntegrityError):
            assign(make_request(), episode, operator)

    def test_a_released_episode_can_be_assigned_again(self, make_episode, make_request, make_user):
        operator = make_user(email="ops@example.com", role="operator")
        episode = make_episode()
        first = assign(make_request(), episode, operator)
        first.released_at, first.released_by = timezone.now(), operator
        first.save()

        second = assign(make_request(), episode, operator)

        assert Assignment.objects.filter(episode=episode).count() == 2  # history is kept
        assert second.released_at is None

    def test_release_time_and_releasing_user_go_together(self, make_episode, make_request, make_user):
        operator = make_user(email="ops@example.com", role="operator")
        assignment = assign(make_request(), make_episode(), operator)
        assignment.released_at = timezone.now()  # without released_by

        with pytest.raises(IntegrityError):
            assignment.save()
