import pytest
from django.conf import settings

from tests.test_auth_login import login

pytestmark = pytest.mark.django_db


def fail(client, email, times):
    for _ in range(times):
        assert login(client, email, "wrong-password").status_code == 401


def test_an_email_is_locked_for_15_minutes_after_five_failed_attempts(api_client, make_user):
    make_user(email="a@example.com")
    fail(api_client, "a@example.com", 5)

    response = login(api_client, "a@example.com")  # even the right password is refused now

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    assert 0 < int(response["Retry-After"]) <= 15 * 60


def test_a_successful_login_resets_the_failure_count(api_client, make_user):
    make_user(email="a@example.com")
    fail(api_client, "a@example.com", 4)
    assert login(api_client, "a@example.com").status_code == 200

    fail(api_client, "a@example.com", 4)

    assert login(api_client, "a@example.com").status_code == 200


def test_locking_one_email_does_not_affect_another(api_client, make_user):
    make_user(email="a@example.com")
    make_user(email="b@example.com")
    fail(api_client, "a@example.com", 5)

    assert login(api_client, "b@example.com").status_code == 200


def test_one_ip_address_gets_ten_attempts_per_minute(api_client):
    for n in range(10):
        assert login(api_client, f"guess{n}@example.com", "x").status_code == 401

    response = login(api_client, "guess10@example.com", "x")

    assert response.status_code == 429
    assert "Retry-After" in response


def test_counters_are_shared_by_all_workers():
    # A per-process memory cache would give an attacker a fresh budget on every gunicorn worker.
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
