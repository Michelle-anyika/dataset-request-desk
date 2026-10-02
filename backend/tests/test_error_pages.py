"""Errors raised outside the API views (no matching URL, a malformed request, a crash) are JSON too.

Before, a URL that matched no route, such as ``/api/requests/0.5/``, got Django's HTML error page: a client
expecting the one error shape would fail to parse it. Found by Schemathesis (docs/testing.md).
"""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client(raise_request_exception=False)


def test_an_unknown_url_is_a_json_404(client):
    response = client.get("/api/requests/0.5/")

    assert response.status_code == 404
    assert response["Content-Type"] == "application/json"
    assert response.json() == {"error": {"code": "not_found", "message": "Not found."}}


def test_a_malformed_request_is_a_json_400(api_as, settings):
    settings.DATA_UPLOAD_MAX_NUMBER_FIELDS = 5  # more fields than this is refused as suspicious
    operator = api_as("operator")
    operator.raise_request_exception = False

    response = operator.get("/api/requests/?" + "&".join(f"f{n}=x" for n in range(10)))

    assert response.status_code == 400
    assert response.json() == {"error": {"code": "bad_request", "message": "Bad request."}}


def test_a_crash_is_a_json_500_without_details(client, monkeypatch):
    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("database password is hunter2")

    monkeypatch.setattr("apps.core.views.connection", BrokenConnection())

    response = client.get("/health")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "server_error", "message": "Something went wrong on our side."}
    }
    assert b"hunter2" not in response.content
