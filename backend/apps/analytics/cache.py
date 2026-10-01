"""Shared analytics cache: computed once, invalidated by a data version, with stampede protection.

Every staff member sees the same numbers for a range, so one computed result can serve everyone. Results live
in the default (database-backed) cache, shared by every worker and container.

- **Correctness comes from invalidation, not expiry.** Results are stored under the current *data version*;
  any change that affects the numbers (a submission, a status change, an import) sets a new version, so old
  results are simply never read again. The lifetime is only a safety net.
- **Stampede protection.** When many requests miss at once, one worker takes a short lock and computes; the
  others wait briefly for its result instead of all running the same heavy aggregation.
"""

import time
import uuid

from django.core.cache import cache

VERSION_KEY = "analytics:data-version"
RESULT_TTL_SECONDS = 300
LOCK_TTL_SECONDS = 30
WAIT_STEP_SECONDS = 0.05
WAIT_LIMIT_SECONDS = 5.0


def data_version() -> str:
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.add(VERSION_KEY, uuid.uuid4().hex, None)  # add: only one worker's first version wins
        version = cache.get(VERSION_KEY)
    return version


def bump_data_version() -> None:
    """Called after every change that affects analytics (on commit, so readers never see a half change)."""
    cache.set(VERSION_KEY, uuid.uuid4().hex, None)


def result_key(name: str) -> str:
    return f"analytics:{data_version()}:{name}"


def lock_key(name: str) -> str:
    return f"analytics-lock:{data_version()}:{name}"


def get_or_compute(name: str, compute):
    key = result_key(name)
    value = cache.get(key)
    if value is not None:
        return value

    lock = lock_key(name)
    if cache.add(lock, "computing", LOCK_TTL_SECONDS):
        try:
            value = compute()
            cache.set(key, value, RESULT_TTL_SECONDS)
            return value
        finally:
            cache.delete(lock)

    waited = 0.0
    while waited < WAIT_LIMIT_SECONDS:
        time.sleep(WAIT_STEP_SECONDS)
        waited += WAIT_STEP_SECONDS
        value = cache.get(key)
        if value is not None:
            return value
    # The computing worker is too slow or died: don't make this user wait any longer.
    return compute()
