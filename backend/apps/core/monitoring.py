"""Error reporting to Sentry (docs/security.md §2). Off unless ``SENTRY_DSN`` is set.

Unhandled errors (and ERROR-level log lines, such as a detected refresh-token theft) reach the team without
anyone reading logs. Events carry the request ID and user ID, never credentials, cookies or request bodies.
"""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

_SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-csrftoken"}


def scrub_event(event, hint):
    """Last line of defence before an event leaves the server."""
    request = event.get("request") or {}
    headers = request.get("headers") or {}
    request["headers"] = {
        name: value for name, value in headers.items() if name.lower() not in _SECRET_HEADERS
    }
    # Cookies hold the refresh token; bodies and query strings may hold passwords or personal data.
    for field in ("cookies", "data", "query_string"):
        request.pop(field, None)
    if "user" in event:
        event["user"] = {"id": event["user"]["id"]} if event["user"].get("id") else {}
    return event


def init_error_reporting(*, dsn: str, environment: str, release: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
        before_send=scrub_event,
        traces_sample_rate=0.0,  # errors only; performance tracing would need its own privacy review
    )
