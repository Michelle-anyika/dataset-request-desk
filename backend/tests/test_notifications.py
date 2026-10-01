"""Notifications on status changes (PLAN.md §7.4)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.catalog.models import Episode, Quality, Robot
from apps.notifications.models import Notification, NotificationKind
from apps.requests_desk.models import Assignment, RequestStatus
from apps.requests_desk.services import submit_request
from apps.requests_desk.workflow import transition

S = RequestStatus
NOTIFICATIONS = "/api/notifications/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(make_user):
    return make_user(email="client@example.com", full_name="Acme Robotics", role="client")


@pytest.fixture
def operators(make_user):
    return [make_user(email=f"ops{n}@example.com", role="operator") for n in (1, 2)]


@pytest.fixture
def submitted(owner, operators, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        return submit_request(
            owner,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=14),
        )


def deliver(request, operator, capture):
    """Move to delivered through the real workflow, assigning one episode so the delivery check passes."""
    robot, _ = Robot.objects.get_or_create(id="arm-01", defaults={"kind": "arm"})
    with capture(execute=True):
        transition(request, to_status=S.IN_PROGRESS, actor=operator)
    episode = Episode.objects.create(
        episode_id=f"EP-{Episode.objects.count() + 1:05d}",
        robot=robot,
        task_name=request.task_name,
        recorded_at=timezone.now(),
        duration_seconds=30,
        quality=Quality.GOOD,
    )
    Assignment.objects.create(request=request, episode=episode, assigned_by=operator)
    with capture(execute=True):
        transition(request, to_status=S.DELIVERED, actor=operator)


def kinds_for(user):
    return [n.kind for n in Notification.objects.filter(recipient=user).order_by("id")]


class TestWhoIsNotified:
    def test_a_new_request_notifies_every_active_operator(self, submitted, operators, owner, make_user):
        inactive = make_user(email="gone@example.com", role="operator", is_active=False)

        assert all(kinds_for(op) == [NotificationKind.REQUEST_SUBMITTED] for op in operators)
        assert kinds_for(owner) == []
        assert kinds_for(inactive) == []
        assert mail.outbox == []  # in-app only

    def test_a_delivery_notifies_and_emails_the_owner(
        self, submitted, operators, owner, django_capture_on_commit_callbacks
    ):
        deliver(submitted, operators[0], django_capture_on_commit_callbacks)

        assert kinds_for(owner) == [NotificationKind.REQUEST_DELIVERED]
        [email] = mail.outbox
        assert email.to == ["client@example.com"]
        assert "pick cup" in email.subject
        assert str(submitted.id) in email.body  # a link to the request
        assert Notification.objects.get(recipient=owner).emailed_at is not None

    def test_a_rejection_notifies_and_emails_the_operator_who_delivered(
        self, submitted, operators, owner, django_capture_on_commit_callbacks
    ):
        deliver(submitted, operators[1], django_capture_on_commit_callbacks)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            transition(submitted, to_status=S.REJECTED, actor=owner, comment="Wrong cup in half the clips.")

        assert kinds_for(operators[1])[-1] == NotificationKind.DELIVERY_REJECTED
        assert NotificationKind.DELIVERY_REJECTED not in kinds_for(operators[0])
        [email] = mail.outbox
        assert email.to == ["ops2@example.com"]
        assert "Wrong cup in half the clips." in email.body

    def test_an_acceptance_notifies_the_delivering_operator_in_app_only(
        self, submitted, operators, owner, django_capture_on_commit_callbacks
    ):
        deliver(submitted, operators[0], django_capture_on_commit_callbacks)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            transition(submitted, to_status=S.ACCEPTED, actor=owner)

        assert kinds_for(operators[0])[-1] == NotificationKind.DELIVERY_ACCEPTED
        assert mail.outbox == []


class TestDelivery:
    def test_a_failed_email_never_breaks_the_status_change(
        self, submitted, operators, owner, django_capture_on_commit_callbacks, monkeypatch
    ):
        from apps.notifications import services

        def smtp_down(*args, **kwargs):
            raise OSError("SMTP server unreachable")

        monkeypatch.setattr(services, "send_mail", smtp_down)

        deliver(submitted, operators[0], django_capture_on_commit_callbacks)

        submitted.refresh_from_db()
        assert submitted.status == S.DELIVERED
        assert Notification.objects.get(recipient=owner).emailed_at is None  # retried by send_reminders

    def test_no_email_is_sent_for_a_change_that_rolls_back(self, submitted, operators, owner):
        # Without running on-commit callbacks (as if the transaction rolled back), nothing is sent.
        transition(submitted, to_status=S.IN_PROGRESS, actor=operators[0])

        assert mail.outbox == []


class TestInbox:
    def test_lists_only_my_notifications_newest_first(self, api_client, submitted, operators):
        api_client.force_authenticate(operators[0])

        results = api_client.get(NOTIFICATIONS).json()["results"]

        assert [r["kind"] for r in results] == ["request_submitted"]
        assert results[0]["request"] == {
            "id": str(submitted.id),
            "task_name": "pick cup",
            "status": "submitted",
        }
        assert "pick cup" in results[0]["message"]
        assert results[0]["read_at"] is None

    def test_marking_read_and_unread_count(self, api_client, submitted, operators):
        api_client.force_authenticate(operators[0])
        [notification] = api_client.get(NOTIFICATIONS).json()["results"]

        assert api_client.get(f"{NOTIFICATIONS}summary/").json() == {"unread": 1}
        assert api_client.post(f"{NOTIFICATIONS}{notification['id']}/read/").status_code == 204
        assert api_client.get(f"{NOTIFICATIONS}summary/").json() == {"unread": 0}
        assert api_client.get(NOTIFICATIONS, {"unread": "true"}).json()["results"] == []

    def test_read_all(self, api_client, submitted, operators, owner, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            submit_request(owner, task_name="fold towel", episodes_requested=1, deadline=timezone.localdate())
        api_client.force_authenticate(operators[0])

        assert api_client.post(f"{NOTIFICATIONS}read-all/").status_code == 204
        assert api_client.get(f"{NOTIFICATIONS}summary/").json() == {"unread": 0}

    def test_another_users_notification_is_not_found(self, api_client, submitted, operators):
        theirs = Notification.objects.get(recipient=operators[1])
        api_client.force_authenticate(operators[0])

        assert api_client.post(f"{NOTIFICATIONS}{theirs.id}/read/").status_code == 404

    def test_requires_authentication(self, api_client):
        assert api_client.get(NOTIFICATIONS).status_code == 401

    def test_listing_uses_a_fixed_number_of_queries(
        self, api_client, owner, operators, django_capture_on_commit_callbacks, django_assert_max_num_queries
    ):
        with django_capture_on_commit_callbacks(execute=True):
            for n in range(15):
                submit_request(
                    owner, task_name=f"task {n}", episodes_requested=1, deadline=timezone.localdate()
                )
        api_client.force_authenticate(operators[0])

        with django_assert_max_num_queries(2):
            api_client.get(NOTIFICATIONS)
