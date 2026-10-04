"""HTTPS-related settings, derived from one switch (docs/security.md §5).

Secure by default: ``HTTPS_ONLY`` is on unless ``DEBUG`` is, so a production deploy can't forget it.
"""

HSTS_SECONDS = 365 * 24 * 60 * 60  # one year


def https_settings(*, enabled: bool) -> dict:
    return {
        "SECURE_SSL_REDIRECT": enabled,
        # The hosting proxy terminates TLS and says so in this header; trusted only when HTTPS is enforced.
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https") if enabled else None,
        "SECURE_HSTS_SECONDS": HSTS_SECONDS if enabled else 0,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": enabled,
        "SECURE_HSTS_PRELOAD": enabled,
        "CSRF_COOKIE_SECURE": enabled,
        "SESSION_COOKIE_SECURE": enabled,
    }
