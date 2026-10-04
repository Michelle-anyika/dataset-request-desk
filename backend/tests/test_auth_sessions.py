from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from tests.test_auth_login import ME, bearer, login

REFRESH = "/api/auth/refresh/"
LOGOUT = "/api/auth/logout/"
LOGOUT_ALL = "/api/auth/logout-all/"

pytestmark = pytest.mark.django_db


def refresh_cookie(client):
    return client.cookies["refresh_token"].value


def use_refresh_cookie(client, token):
    client.cookies["refresh_token"] = token


def jti(token):
    return RefreshToken(token, verify=False)["jti"]


def age_blacklist_entries(by=timedelta(minutes=1)):
    BlacklistedToken.objects.update(blacklisted_at=timezone.now() - by)


class TestRefresh:
    def test_rotates_the_cookie_and_returns_a_new_access_token(self, api_client, make_user):
        make_user(email="a@example.com")
        login(api_client, "a@example.com")
        old = refresh_cookie(api_client)

        response = api_client.post(REFRESH)

        assert response.status_code == 200
        assert set(response.json()) == {"access"}
        new = response.cookies["refresh_token"].value
        assert new
        assert new != old
        assert BlacklistedToken.objects.filter(token__jti=jti(old)).exists()
        bearer(api_client, response.json()["access"])
        assert api_client.get(ME).status_code == 200

    def test_requires_the_refresh_cookie(self, api_client):
        response = api_client.post(REFRESH)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    def test_rejects_and_clears_a_tampered_cookie(self, api_client):
        use_refresh_cookie(api_client, "not-a-real-token")

        response = api_client.post(REFRESH)

        assert response.status_code == 401
        assert response.cookies["refresh_token"].value == ""

    def test_an_access_token_cannot_be_used_as_a_refresh_token(self, api_client, make_user):
        make_user(email="a@example.com")
        use_refresh_cookie(api_client, login(api_client, "a@example.com").json()["access"])

        assert api_client.post(REFRESH).status_code == 401

    def test_rejected_for_a_deactivated_user(self, api_client, make_user):
        user = make_user(email="a@example.com")
        login(api_client, "a@example.com")
        user.is_active = False
        user.save()

        assert api_client.post(REFRESH).status_code == 401


class TestReuseDetection:
    def test_reusing_a_rotated_token_revokes_every_session(self, api_client, make_user):
        make_user(email="a@example.com")
        login(api_client, "a@example.com")
        stolen = refresh_cookie(api_client)
        rotated = api_client.post(REFRESH)
        legitimate = refresh_cookie(api_client)
        age_blacklist_entries()  # well past the grace period: this is a replay, not a race

        use_refresh_cookie(api_client, stolen)
        response = api_client.post(REFRESH)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_revoked"
        use_refresh_cookie(api_client, legitimate)
        assert api_client.post(REFRESH).status_code == 401  # the legitimate session ended too
        bearer(api_client, rotated.json()["access"])
        assert api_client.get(ME).status_code == 401  # and so did its access token

    def test_reuse_within_the_grace_period_is_treated_as_a_race(self, api_client, make_user):
        # Two tabs refreshing at once both send the old cookie; the slower one must not end the session.
        make_user(email="a@example.com")
        login(api_client, "a@example.com")
        old = refresh_cookie(api_client)
        api_client.post(REFRESH)
        new = refresh_cookie(api_client)

        use_refresh_cookie(api_client, old)
        assert api_client.post(REFRESH).status_code == 401

        use_refresh_cookie(api_client, new)
        assert api_client.post(REFRESH).status_code == 200


class TestLogout:
    def test_blacklists_the_refresh_token_and_clears_the_cookie(self, api_client, make_user):
        make_user(email="a@example.com")
        login(api_client, "a@example.com")
        old = refresh_cookie(api_client)

        response = api_client.post(LOGOUT)

        assert response.status_code == 204
        assert response.cookies["refresh_token"].value == ""
        assert response.cookies["refresh_token"]["max-age"] == 0
        use_refresh_cookie(api_client, old)
        assert api_client.post(REFRESH).status_code == 401

    def test_succeeds_without_a_session(self, api_client):
        assert api_client.post(LOGOUT).status_code == 204

    def test_logout_all_ends_every_session_of_the_user(self, make_user):
        make_user(email="a@example.com")
        laptop, phone = APIClient(), APIClient()
        laptop_access = login(laptop, "a@example.com").json()["access"]
        login(phone, "a@example.com")
        bearer(laptop, laptop_access)

        assert laptop.post(LOGOUT_ALL).status_code == 204

        assert phone.post(REFRESH).status_code == 401
        assert laptop.get(ME).status_code == 401
        bearer(laptop, login(laptop, "a@example.com").json()["access"])
        assert laptop.get(ME).status_code == 200  # logging in again straight away works

    def test_logout_all_requires_authentication(self, api_client):
        assert api_client.post(LOGOUT_ALL).status_code == 401
