"""API-wide rate limits (docs/security.md §2).

These run on every request, so they count in process memory rather than the database cache: a shared
counter would cost two queries per API call. Each gunicorn worker therefore has its own budget, which is
fine for coarse abuse protection. Login, where precision matters, uses the shared database-backed
counters (``apps.accounts.throttling``).
"""

from django.core.cache import caches
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AnonBurstThrottle(AnonRateThrottle):
    cache = caches["local"]


class UserSustainedThrottle(UserRateThrottle):
    cache = caches["local"]
