"""Reminders, escalations and deadline warnings from ``send_reminders`` (PLAN.md §7.4)."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.notifications.models import Notification, NotificationKind
from apps.notifications.reminders import send_reminders
from apps.requests_desk.models import DatasetRequest, RequestStatus, RequestStatusEvent

S = RequestStatus
K = NotificationKind
DAY = timedelta(days=1)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(make_user):
    return make_user(email="client@example.com", role="client")


@pytest.fixture
def operator(make_user):
    return make_user(email="ops@example.com", role="operator")


@pytest.fixture
def delivered(owner, operator):
    """A request delivered by ``operator`` at a known time, built without the workflow's side effects."""
    delivered_at = timezone.now() - timedelta(minutes=1)
    request = DatasetRequest.objects.create(
        client=owner,
        task_name="pick cup",
        episodes_requested=1,
        deadline=timezone.localdate() + timedelta(days=60),
        status=S.DELIVERED,
        status_changed_at=delivered_at,
    )
    RequestStatusEvent.objects.create(
        request=request,
        from_status=S.IN_PROGRESS,
        to_status=S.DELIVERED,
        changed_by=operator,
        changed_at=delivered_at,
    )
    return request


def kinds(user, request=None):
    queryset = Notification.objects.filter(recipient=user)
    if request:
        queryset = queryset.filter(request=request)
    return [n.kind for n in queryset.order_by("id")]


class TestReviewReminders:
    def test_nothing_before_three_days(self, delivered, owner):
        send_reminders(now=timezone.now() + 2 * DAY)

        assert kinds(owner) == []

    def test_a_reminder_after_three_days_by_email_and_in_app(self, delivered, owner):
        send_reminders(now=timezone.now() + 3 * DAY)

        assert kinds(owner) == [K.REVIEW_REMINDER]
        [email] = mail.outbox
        assert email.to == ["client@example.com"]
        assert "waiting for your decision" in email.subject

    def test_running_again_sends_nothing_extra(self, delivered, owner):
        now = timezone.now() + 3 * DAY
        send_reminders(now=now)

        send_reminders(now=now + timedelta(hours=1))

        assert kinds(owner) == [K.REVIEW_REMINDER]
        assert len(mail.outbox) == 1

    def test_every_three_days_at_most_three_then_the_operator_takes_over(self, delivered, owner, operator):
        start = timezone.now()
        for days in (3, 6, 9, 12, 15, 18):
            send_reminders(now=start + days * DAY)

        assert kinds(owner) == [K.REVIEW_REMINDER] * 3
        assert kinds(operator) == [K.REVIEW_ESCALATION]  # once, not again on day 15 or 18
        assert [e.to for e in mail.outbox] == [["client@example.com"]] * 3 + [["ops@example.com"]]

    def test_no_reminders_once_decided(self, delivered, owner):
        DatasetRequest.objects.filter(pk=delivered.pk).update(status=S.ACCEPTED)

        send_reminders(now=timezone.now() + 10 * DAY)

        assert kinds(owner) == []

    def test_a_new_delivery_after_rework_starts_the_count_again(self, delivered, owner, operator):
        start = timezone.now()
        for days in (3, 6, 9):
            send_reminders(now=start + days * DAY)
        redelivered_at = start + 10 * DAY
        DatasetRequest.objects.filter(pk=delivered.pk).update(
            status=S.DELIVERED, status_changed_at=redelivered_at
        )

        send_reminders(now=redelivered_at + 3 * DAY)

        assert kinds(owner) == [K.REVIEW_REMINDER] * 4


class TestDeadlineWarnings:
    @pytest.fixture
    def due_soon(self, owner):
        return DatasetRequest.objects.create(
            client=owner,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + 2 * DAY,
            status=S.IN_PROGRESS,
        )

    def test_operators_are_warned_once_two_days_before_the_deadline(self, due_soon, operator, make_user):
        other = make_user(email="ops2@example.com", role="operator")

        send_reminders(now=timezone.now())
        send_reminders(now=timezone.now() + timedelta(hours=5))

        assert kinds(operator, due_soon) == [K.DEADLINE_APPROACHING]
        assert kinds(other, due_soon) == [K.DEADLINE_APPROACHING]
        assert mail.outbox == []  # in-app only

    @pytest.mark.parametrize("status", [S.DELIVERED, S.ACCEPTED])
    def test_not_for_requests_already_delivered(self, due_soon, operator, status):
        DatasetRequest.objects.filter(pk=due_soon.pk).update(status=status)

        send_reminders(now=timezone.now())

        assert kinds(operator, due_soon) == []

    def test_not_for_distant_deadlines(self, due_soon, operator):
        DatasetRequest.objects.filter(pk=due_soon.pk).update(deadline=timezone.localdate() + 10 * DAY)

        send_reminders(now=timezone.now())

        assert kinds(operator, due_soon) == []


def test_reminder_runs_cost_a_fixed_number_of_queries(owner, operator, django_assert_max_num_queries):
    """Requests that need nothing must not cost queries each: the check is done in SQL for all at once."""
    for _ in range(25):
        DatasetRequest.objects.create(
            client=owner,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=60),
            status=S.DELIVERED,
            status_changed_at=timezone.now(),
        )

    with django_assert_max_num_queries(4):  # waiting deliveries, due deadlines, operators, pending emails
        send_reminders(now=timezone.now() + timedelta(hours=1))


def test_unsent_emails_are_retried(delivered, owner):
    stuck = Notification.objects.create(
        recipient=owner,
        request=delivered,
        kind=K.REQUEST_DELIVERED,
        created_at=timezone.now() - timedelta(hours=1),
    )

    send_reminders(now=timezone.now())

    stuck.refresh_from_db()
    assert stuck.emailed_at is not None
    assert [e.to for e in mail.outbox] == [["client@example.com"]]


def test_the_command_reports_what_it_did(delivered):
    out = StringIO()

    call_command("send_reminders", stdout=out)

    assert "reminders" in out.getvalue()
