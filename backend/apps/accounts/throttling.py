"""Brute-force protection for login (docs/security.md §3).

Both limits keep their counters in the default cache, which is database-backed so every gunicorn worker and
container shares them.
"""

import hashlib
import time

from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

FAILURE_LIMIT = 5
FAILURE_WINDOW_SECONDS = 15 * 60


class LoginRateThrottle(SimpleRateThrottle):
    """Every login attempt from one IP address, successful or not: slows down spraying many accounts."""

    scope = "login"
    rate = "10/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def _failures_key(email: str) -> str:
    # Hashed so the cache table never holds email addresses.
    return "login-failures:" + hashlib.sha256(email.encode()).hexdigest()


def _recent_failures(email: str, now: float) -> list[float]:
    return [t for t in cache.get(_failures_key(email), []) if t > now - FAILURE_WINDOW_SECONDS]


def lockout_seconds(email: str) -> int | None:
    """Seconds until this email may try again, or None if it isn't locked."""
    now = time.time()
    failures = _recent_failures(email, now)
    if len(failures) < FAILURE_LIMIT:
        return None
    return max(1, int(failures[0] + FAILURE_WINDOW_SECONDS - now))


def record_failure(email: str) -> None:
    now = time.time()
    cache.set(_failures_key(email), [*_recent_failures(email, now), now], FAILURE_WINDOW_SECONDS)


def clear_failures(email: str) -> None:
    cache.delete(_failures_key(email))
