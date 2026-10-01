"""Error reporting to Sentry (#32): off unless configured, and never sends personal data or secrets."""

import pytest
import sentry_sdk

from apps.core import monitoring
from tests.test_auth_login import ME, bearer, login


@pytest.fixture
def no_real_sentry(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    return calls


def test_nothing_is_initialised_without_a_dsn(no_real_sentry):
    monitoring.init_error_reporting(dsn="", environment="dev", release="abc")

    assert no_real_sentry == []


def test_initialised_without_default_personal_data(no_real_sentry):
    monitoring.init_error_reporting(
        dsn="https://key@example.ingest.sentry.io/1", environment="prod", release="abc"
    )

    [options] = no_real_sentry
    assert options["send_default_pii"] is False
    assert options["environment"] == "prod"
    assert options["release"] == "abc"
    assert options["before_send"] is monitoring.scrub_event


def test_secrets_and_bodies_are_removed_before_sending():
    event = {
        "request": {
            "headers": {"Authorization": "Bearer abc", "Cookie": "refresh_token=xyz", "User-Agent": "test"},
            "cookies": {"refresh_token": "xyz"},
            "data": {"email": "a@example.com", "password": "hunter2"},
            "query_string": "token=abc",
        },
        "user": {"id": "42", "email": "a@example.com", "ip_address": "10.0.0.1"},
    }

    scrubbed = monitoring.scrub_event(event, hint={})

    request = scrubbed["request"]
    assert "Authorization" not in request["headers"]
    assert "Cookie" not in request["headers"]
    assert request["headers"]["User-Agent"] == "test"
    assert "cookies" not in request
    assert "data" not in request
    assert "query_string" not in request
    assert scrubbed["user"] == {"id": "42"}


@pytest.mark.django_db
def test_events_carry_the_request_id(client, monkeypatch):
    tags = {}
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda key, value: tags.update({key: value}))

    response = client.get("/health")

    assert tags["request_id"] == response["X-Request-ID"]


@pytest.mark.django_db
def test_events_carry_the_authenticated_user_id_only(api_client, make_user, monkeypatch):
    users = []
    monkeypatch.setattr(sentry_sdk, "set_user", users.append)
    user = make_user(email="a@example.com")
    bearer(api_client, login(api_client, "a@example.com").json()["access"])

    api_client.get(ME)

    assert users[-1] == {"id": str(user.pk)}
