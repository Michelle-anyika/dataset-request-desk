"""Business dates follow the company's time zone (Africa/Kigali, UTC+2), while timestamps stay in UTC.

Between 00:00 and 02:00 in Kigali it is still "yesterday" in UTC: rules about today's date must use Kigali.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.core.dates import business_today
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.reminders import send_reminders
from apps.requests_desk.models import DatasetRequest, RequestStatus

# 00:30 on 2 October in Kigali.
JUST_AFTER_MIDNIGHT_IN_KIGALI = datetime(2026, 10, 1, 22, 30, tzinfo=UTC)

pytestmark = pytest.mark.django_db


@pytest.fixture
def kigali_half_past_midnight(monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "now", lambda: JUST_AFTER_MIDNIGHT_IN_KIGALI)


def test_business_today_is_the_kigali_date(kigali_half_past_midnight):
    assert business_today() == date(2026, 10, 2)


def test_a_deadline_of_yesterday_in_kigali_is_refused(api_as, kigali_half_past_midnight):
    response = api_as("client").post(
        "/api/requests/",
        {"task_name": "pick cup", "episodes_requested": 5, "deadline": "2026-10-01"},
        format="json",
    )

    assert response.status_code == 400
    assert "deadline" in response.json()["error"]["details"]


def test_a_deadline_of_today_in_kigali_is_accepted(api_as, kigali_half_past_midnight):
    response = api_as("client").post(
        "/api/requests/",
        {"task_name": "pick cup", "episodes_requested": 5, "deadline": "2026-10-02"},
        format="json",
    )

    assert response.status_code == 201


def test_deadline_warnings_count_days_in_kigali(make_user):
    operator = make_user(email="ops@example.com", role="operator")
    request = DatasetRequest.objects.create(
        client=make_user(email="c@example.com"),
        task_name="pick cup",
        episodes_requested=1,
        deadline=date(2026, 10, 4),  # two days after 2 October in Kigali; three after 1 October in UTC
        status=RequestStatus.IN_PROGRESS,
    )

    send_reminders(now=JUST_AFTER_MIDNIGHT_IN_KIGALI)

    assert Notification.objects.filter(
        recipient=operator, request=request, kind=NotificationKind.DEADLINE_APPROACHING
    ).exists()


def test_analytics_default_range_ends_on_the_kigali_date(api_as, kigali_half_past_midnight):
    body = api_as("operator").get("/api/analytics/").json()

    assert body["range"]["to"] == "2026-10-02"
    assert date.fromisoformat(body["range"]["from"]) == date(2026, 10, 2) - timedelta(days=29)
