import pytest
from django.conf import settings

from tests.conftest import DEFAULT_PASSWORD
from tests.test_auth_sessions import LOGOUT, REFRESH

LOGIN = "/api/auth/login/"

pytestmark = pytest.mark.django_db

# Browsers set Sec-Fetch-Site on every request; another site's page can't forge or remove it.
CROSS_SITE = {"HTTP_SEC_FETCH_SITE": "cross-site"}


@pytest.mark.parametrize("path", [LOGIN, REFRESH, LOGOUT])
def test_cookie_endpoints_refuse_requests_started_by_another_site(api_client, make_user, path):
    make_user(email="a@example.com")
    api_client.post(LOGIN, {"email": "a@example.com", "password": DEFAULT_PASSWORD}, format="json")

    response = api_client.post(
        path, {"email": "a@example.com", "password": DEFAULT_PASSWORD}, format="json", **CROSS_SITE
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "cross_site_request"


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_same_origin_and_direct_requests_are_allowed(api_client, make_user, site):
    make_user(email="a@example.com")

    response = api_client.post(
        LOGIN,
        {"email": "a@example.com", "password": DEFAULT_PASSWORD},
        format="json",
        HTTP_SEC_FETCH_SITE=site,
    )

    assert response.status_code == 200


def test_django_csrf_middleware_is_enabled_for_non_api_views():
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
