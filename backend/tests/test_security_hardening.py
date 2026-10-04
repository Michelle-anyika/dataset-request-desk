"""Production hardening (docs/security.md §5)."""

import pytest
from django.conf import settings

from config.security import https_settings

pytestmark = pytest.mark.django_db

API_CSP = "default-src 'none'; frame-ancestors 'none'"


class TestDefensiveHeaders:
    @pytest.mark.parametrize("path", ["/health", "/api/auth/me/"])
    def test_every_response_carries_them(self, client, path):
        response = client.get(path)

        assert response["Content-Security-Policy"] == API_CSP
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "same-origin"
        assert response["Cross-Origin-Opener-Policy"] == "same-origin"

    def test_the_docs_page_may_load_its_assets_but_still_cannot_be_framed(self, client, settings):
        settings.API_DOCS_ENABLED = True

        csp = client.get("/api/docs/")["Content-Security-Policy"]

        # Parsed per directive: the CDN must be allowed exactly where Swagger UI loads from, nowhere else.
        directives = dict((part.split()[0], part.split()[1:]) for part in csp.split(";") if part.strip())
        for directive in ("script-src", "style-src", "img-src"):
            assert "https://cdn.jsdelivr.net" in directives[directive]
        assert "https://cdn.jsdelivr.net" not in directives["default-src"]
        assert directives["frame-ancestors"] == ["'none'"]


class TestHttpsSettings:
    def test_https_is_enforced_when_enabled(self):
        values = https_settings(enabled=True)

        assert values["SECURE_SSL_REDIRECT"] is True
        assert values["SECURE_HSTS_SECONDS"] == 365 * 24 * 60 * 60
        assert values["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is True
        assert values["CSRF_COOKIE_SECURE"] is True
        assert values["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")

    def test_nothing_is_forced_when_disabled(self):
        values = https_settings(enabled=False)

        assert values["SECURE_SSL_REDIRECT"] is False
        assert values["SECURE_HSTS_SECONDS"] == 0

    def test_http_is_redirected_to_https_but_health_checks_are_not(self, client, settings):
        settings.SECURE_SSL_REDIRECT = True

        assert client.get("/api/auth/me/").status_code == 301
        # Hosting platforms call the health check over plain HTTP inside their network.
        assert client.get("/health").status_code == 200

    def test_https_defaults_to_on_outside_debug(self):
        from config.settings import HTTPS_ONLY  # noqa: F401  the setting exists and drives https_settings

        assert settings.SECURE_REDIRECT_EXEMPT == [r"^health$"]


class TestRateLimits:
    def test_anonymous_callers_are_limited(self, api_client):
        for _ in range(60):
            api_client.post("/api/auth/refresh/")

        assert api_client.post("/api/auth/refresh/").status_code == 429

    def test_authenticated_users_have_a_rate_limit(self):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        assert rates["anon"] == "60/min"
        assert rates["user"] == "3000/hour"

    def test_general_limits_do_not_add_database_queries(self, api_as, django_assert_max_num_queries):
        # Per-request limits use process memory; only login throttling pays for the shared database cache.
        client = api_as("client")

        with django_assert_max_num_queries(2):
            client.get("/api/requests/")
