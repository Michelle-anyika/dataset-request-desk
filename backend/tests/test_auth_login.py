import pytest
from rest_framework_simplejwt.tokens import AccessToken

from tests.conftest import DEFAULT_PASSWORD

LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"

pytestmark = pytest.mark.django_db


def login(client, email, password=DEFAULT_PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


def bearer(client, access):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")


class TestLogin:
    def test_returns_access_token_and_profile_and_sets_refresh_cookie(self, api_client, make_user):
        user = make_user(email="ops1@example.com", role="operator", full_name="Olu Operator")

        response = login(api_client, "ops1@example.com")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access", "user"}  # the refresh token never appears in a response body
        assert body["user"] == {
            "id": str(user.id),
            "email": "ops1@example.com",
            "full_name": "Olu Operator",
            "role": "operator",
            "organisation": "",
        }
        cookie = response.cookies["refresh_token"]
        assert cookie.value
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Strict"
        assert cookie["path"] == "/api/auth/"
        assert cookie["max-age"] == 12 * 60 * 60

    def test_access_token_lives_ten_minutes(self, api_client, make_user):
        make_user(email="ops1@example.com")

        token = AccessToken(login(api_client, "ops1@example.com").json()["access"])

        assert token["exp"] - token["iat"] == 10 * 60

    def test_email_is_case_insensitive(self, api_client, make_user):
        make_user(email="ops1@example.com")

        assert login(api_client, "  OPS1@Example.com ").status_code == 200

    def test_wrong_password_and_unknown_email_get_the_same_answer(self, api_client, make_user):
        make_user(email="ops1@example.com")

        wrong_password = login(api_client, "ops1@example.com", "not-the-password")
        unknown_email = login(api_client, "nobody@example.com")

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()
        assert wrong_password.json() == {
            "error": {"code": "invalid_credentials", "message": "Email or password is incorrect."}
        }

    def test_inactive_user_cannot_log_in(self, api_client, make_user):
        make_user(email="gone@example.com", is_active=False)

        response = login(api_client, "gone@example.com")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_missing_fields_are_reported_per_field(self, api_client):
        response = api_client.post(LOGIN, {"email": "not-an-email"}, format="json")

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid"
        assert set(error["details"]) == {"email", "password"}


class TestAccessToken:
    def test_endpoints_require_authentication_by_default(self, api_client):
        response = api_client.get(ME)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    def test_me_returns_the_current_user(self, api_client, make_user):
        make_user(email="client-a@example.com", organisation="Acme Robotics")
        bearer(api_client, login(api_client, "client-a@example.com").json()["access"])

        response = api_client.get(ME)

        assert response.status_code == 200
        assert response.json()["email"] == "client-a@example.com"
        assert response.json()["organisation"] == "Acme Robotics"

    def test_malformed_token_is_rejected(self, api_client):
        bearer(api_client, "not-a-jwt")

        assert api_client.get(ME).status_code == 401

    def test_deactivated_user_is_rejected_even_with_a_valid_token(self, api_client, make_user):
        user = make_user(email="client-a@example.com")
        bearer(api_client, login(api_client, "client-a@example.com").json()["access"])

        user.is_active = False
        user.save()

        assert api_client.get(ME).status_code == 401

    def test_tokens_from_a_revoked_session_are_rejected_immediately(self, api_client, make_user):
        user = make_user(email="client-a@example.com")
        bearer(api_client, login(api_client, "client-a@example.com").json()["access"])

        user.session_version += 1  # what revocation does; exact, unlike comparing one-second timestamps
        user.save()

        response = api_client.get(ME)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_revoked"

    def test_logging_in_again_after_revocation_works(self, api_client, make_user):
        user = make_user(email="client-a@example.com")
        user.session_version = 3
        user.save()

        bearer(api_client, login(api_client, "client-a@example.com").json()["access"])

        assert api_client.get(ME).status_code == 200
