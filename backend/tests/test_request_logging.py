import json
import logging
import re
import sys
from types import SimpleNamespace

import pytest
from django.http import HttpResponse

from apps.core.logging import JsonFormatter
from apps.core.middleware import REQUEST_ID_HEADER, RequestLoggingMiddleware

LOGGER = "desk.request"


def handle(request, status=200, user=None):
    """Run a request through the middleware with a stub view."""

    def view(req):
        if user is not None:
            req.user = user  # what authentication does further down the stack
        return HttpResponse(status=status)

    return RequestLoggingMiddleware(view)(request)


@pytest.fixture
def request_log(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    return lambda: [record for record in caplog.records if record.name == LOGGER]


class TestRequestLogLine:
    def test_one_line_per_request_with_required_fields(self, rf, request_log):
        handle(rf.get("/api/requests/", {"status": "submitted"}))

        [record] = request_log()
        assert record.method == "GET"
        assert record.path == "/api/requests/"  # query string left out: it can carry tokens or personal data
        assert record.status == 200
        assert isinstance(record.duration_ms, float)
        assert record.duration_ms >= 0
        assert record.user_id is None

    def test_includes_user_id_when_authenticated(self, rf, request_log):
        user = SimpleNamespace(pk="8d6f1f7e-3c2a-4b1e-9f0a-2d9c1b7e5a44", is_authenticated=True)

        handle(rf.post("/api/requests/"), user=user)

        [record] = request_log()
        assert record.user_id == "8d6f1f7e-3c2a-4b1e-9f0a-2d9c1b7e5a44"

    @pytest.mark.parametrize(
        ("status", "level"),
        [(200, logging.INFO), (302, logging.INFO), (404, logging.WARNING), (500, logging.ERROR)],
    )
    def test_level_follows_response_status(self, rf, request_log, status, level):
        handle(rf.get("/anything"), status=status)

        [record] = request_log()
        assert record.levelno == level

    @pytest.mark.django_db
    def test_is_installed_for_every_request(self, client, request_log):
        client.get("/health")

        [record] = request_log()
        assert record.path == "/health"


class TestRequestId:
    def test_generated_when_missing_and_returned_in_response(self, rf, request_log):
        response = handle(rf.get("/health"))

        [record] = request_log()
        assert re.fullmatch(r"[0-9a-f]{32}", response[REQUEST_ID_HEADER])
        assert record.request_id == response[REQUEST_ID_HEADER]

    def test_reuses_a_safe_incoming_id(self, rf, request_log):
        response = handle(rf.get("/health", HTTP_X_REQUEST_ID="edge-7f3a_01.2"))

        [record] = request_log()
        assert response[REQUEST_ID_HEADER] == "edge-7f3a_01.2"
        assert record.request_id == "edge-7f3a_01.2"

    @pytest.mark.parametrize("unsafe", ["line\nbreak", "has space", "x" * 129, ""])
    def test_replaces_an_unsafe_incoming_id(self, rf, unsafe):
        # Prevents log injection and unbounded values from untrusted clients.
        response = handle(rf.get("/health", HTTP_X_REQUEST_ID=unsafe))

        assert re.fullmatch(r"[0-9a-f]{32}", response[REQUEST_ID_HEADER])


class TestJsonFormatter:
    def make_record(self, **extra):
        record = logging.LogRecord("desk.request", logging.INFO, __file__, 1, "GET /health 200", None, None)
        record.__dict__.update(extra)
        return record

    def test_formats_one_json_object_per_line(self):
        line = JsonFormatter().format(self.make_record(method="GET", status=200, user_id=None))

        assert "\n" not in line
        data = json.loads(line)
        assert data["level"] == "INFO"
        assert data["logger"] == "desk.request"
        assert data["message"] == "GET /health 200"
        assert data["method"] == "GET"
        assert data["status"] == 200
        assert data["user_id"] is None
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", data["ts"])

    def test_includes_exception_details(self):
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord("app", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())

        data = json.loads(JsonFormatter().format(record))

        assert "ValueError: boom" in data["exc_info"]
