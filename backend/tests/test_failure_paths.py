"""The code that only runs on a bad day: fallbacks, malformed input and defensive branches.

Found by the coverage report; each one is a path a user can actually reach.
"""

from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.management import CommandError, call_command
from django.http import Http404, QueryDict
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.accounts import sessions
from apps.analytics import cache as analytics_cache
from apps.catalog.import_service import ImportFailed
from apps.catalog.importing import RowRejected
from apps.core import idempotency
from apps.core.exceptions import api_exception_handler
from apps.core.models import IdempotencyKey
from apps.core.monitoring import scrub_event
from apps.notifications.models import Notification, NotificationKind
from apps.requests_desk.services import submit_request
from tests.test_import_parsing import parse
from tests.test_import_service import ROW_1, operator, robots, run  # noqa: F401 (operator, robots: fixtures)

pytestmark = pytest.mark.django_db


class TestAnalyticsCache:
    def test_a_stuck_computation_does_not_keep_others_waiting(self, monkeypatch):
        # Another worker holds the lock but never publishes (it died): after the wait limit, compute here.
        analytics_cache.cache.add(analytics_cache.lock_key("range"), "dead-worker", 30)
        monkeypatch.setattr(analytics_cache.time, "sleep", lambda seconds: None)

        assert analytics_cache.get_or_compute("range", lambda: {"answer": 42}) == {"answer": 42}


class TestErrorShape:
    @pytest.mark.parametrize(
        ("exc", "status", "code"),
        [(Http404(), 404, "not_found"), (DjangoPermissionDenied(), 403, "permission_denied")],
    )
    def test_django_exceptions_get_the_api_error_shape(self, exc, status, code):
        response = api_exception_handler(exc, {})

        assert response.status_code == status
        assert response.data["error"]["code"] == code

    def test_an_unexpected_error_is_left_to_django(self):
        # No API body that could leak internals: Django answers a bare 500 and logs the traceback.
        assert api_exception_handler(ValueError("database password is hunter2"), {}) is None


class TestIdempotency:
    def request(self, user, data):
        return SimpleNamespace(user=user, method="POST", path="/api/requests/", data=data)

    def test_an_error_response_is_not_remembered(self, make_user):
        user = make_user()

        response = idempotency.run_once(self.request(user, {}), "key-1", lambda: Response(status=400))

        assert response.status_code == 400
        assert not IdempotencyKey.objects.exists()

    def test_form_fields_are_part_of_the_fingerprint(self, make_user):
        user = make_user()
        one = idempotency._fingerprint(self.request(user, QueryDict("note=a")))
        other = idempotency._fingerprint(self.request(user, QueryDict("note=b")))

        assert one != other

    def test_the_purge_command_reports_what_it_deleted(self):
        out = StringIO()

        call_command("purge_idempotency_keys", stdout=out)

        assert out.getvalue().strip() == "0 expired idempotency keys deleted."


class TestSessions:
    def test_a_refresh_token_with_no_server_record_is_refused(self, make_user):
        # Signed by us and unexpired, but its record is gone (e.g. purged): it cannot be trusted.
        _, refresh = sessions.issue_tokens(make_user())
        OutstandingToken.objects.all().delete()

        with pytest.raises(AuthenticationFailed):
            sessions.rotate_session(refresh)

    def test_logging_out_with_a_garbage_cookie_ends_nothing(self):
        assert sessions.end_session("not-a-token") is None


class TestImports:
    def test_a_file_the_csv_module_cannot_read_is_refused(self, operator):  # noqa: F811
        huge_field = "x" * 200_000  # beyond the csv module's field size limit

        with pytest.raises(ImportFailed, match="not valid CSV"):
            run(operator, ROW_1.replace("Aline", huge_field))

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_a_duration_that_is_not_a_finite_number_is_rejected(self, value):
        with pytest.raises(RowRejected) as rejected:
            parse(duration_seconds=value)

        assert rejected.value.code == "invalid_duration"

    def test_the_command_reports_a_missing_file(self, operator):  # noqa: F811
        with pytest.raises(CommandError):
            call_command("import_episodes", "/no/such/export.csv", "--as", operator.email, stdout=StringIO())


class TestErrorReporting:
    def test_events_without_a_user_are_scrubbed_too(self):
        event = scrub_event({"request": {"headers": {"Cookie": "refresh=secret"}, "data": "pw"}}, None)

        assert event == {"request": {"headers": {}}}


class TestNotifications:
    def test_marking_a_read_notification_read_again_keeps_the_first_time(self, api_as):
        client = api_as("client")
        deadline = timezone.localdate() + timedelta(days=9)
        request = submit_request(client.user, task_name="pick cup", episodes_requested=1, deadline=deadline)
        notification = Notification.objects.create(
            recipient=client.user, request=request, kind=NotificationKind.REQUEST_DELIVERED
        )
        client.post(f"/api/notifications/{notification.id}/read/")
        first_read_at = Notification.objects.get(pk=notification.pk).read_at

        assert client.post(f"/api/notifications/{notification.id}/read/").status_code == 204
        assert Notification.objects.get(pk=notification.pk).read_at == first_read_at
