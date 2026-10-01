import hashlib
import logging

import pytest

from tests.test_auth_login import bearer, login
from tests.test_auth_sessions import LOGOUT, LOGOUT_ALL, REFRESH, age_blacklist_entries, use_refresh_cookie

pytestmark = pytest.mark.django_db


@pytest.fixture
def security_log(caplog):
    caplog.set_level(logging.INFO, logger="desk.security")
    return lambda: [record for record in caplog.records if record.name == "desk.security"]


def only_event(records, name):
    [record] = [r for r in records if r.event == name]
    return record


def test_successful_login_is_logged_with_user_and_request(api_client, make_user, security_log):
    user = make_user(email="a@example.com")

    login(api_client, "a@example.com")

    record = only_event(security_log(), "auth.login_succeeded")
    assert record.user_id == str(user.id)
    assert record.client_ip == "127.0.0.1"
    assert len(record.request_id) == 32


def test_failed_login_logs_a_hash_of_the_email_and_never_the_password(api_client, security_log):
    login(api_client, "a@example.com", "hunter2-wrong-password")

    record = only_event(security_log(), "auth.login_failed")
    assert record.levelno == logging.WARNING
    assert record.email_hash == hashlib.sha256(b"a@example.com").hexdigest()
    logged = str(vars(record))
    assert "a@example.com" not in logged
    assert "hunter2-wrong-password" not in logged


def test_logouts_are_logged(api_client, make_user, security_log):
    user = make_user(email="a@example.com")
    bearer(api_client, login(api_client, "a@example.com").json()["access"])

    api_client.post(LOGOUT)
    api_client.post(LOGOUT_ALL)

    assert only_event(security_log(), "auth.logout").user_id == str(user.id)
    assert only_event(security_log(), "auth.logout_all").user_id == str(user.id)


def test_refresh_token_reuse_is_logged_as_an_error(api_client, make_user, security_log):
    user = make_user(email="a@example.com")
    login(api_client, "a@example.com")
    stolen = api_client.cookies["refresh_token"].value
    api_client.post(REFRESH)
    age_blacklist_entries()

    use_refresh_cookie(api_client, stolen)
    api_client.post(REFRESH)

    record = only_event(security_log(), "auth.refresh_reuse_detected")
    assert record.levelno == logging.ERROR  # errors reach error tracking, so a theft alerts someone
    assert record.user_id == str(user.id)


def test_throttled_logins_are_logged(api_client, security_log):
    for n in range(11):
        login(api_client, f"guess{n}@example.com", "x")

    assert only_event(security_log(), "auth.throttled").levelno == logging.WARNING
