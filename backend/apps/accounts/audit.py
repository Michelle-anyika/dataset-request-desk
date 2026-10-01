"""Security audit events on the ``desk.security`` logger (docs/security.md §3).

Each event carries the request ID and client IP. Emails are hashed and passwords are never logged.
"""

import hashlib
import logging

from rest_framework.throttling import BaseThrottle

logger = logging.getLogger("desk.security")


def email_hash(email: str) -> str:
    """Lets failures for one account be correlated without storing the address."""
    return hashlib.sha256(email.encode()).hexdigest()


def client_ip(request) -> str | None:
    # Same proxy-aware lookup as the throttles (REST_FRAMEWORK["NUM_PROXIES"]).
    return BaseThrottle().get_ident(request)


def security_event(event: str, request, *, level: int = logging.INFO, **fields) -> None:
    logger.log(
        level,
        event,
        extra={
            "event": event,
            "request_id": getattr(request, "request_id", None),
            "client_ip": client_ip(request),
            **fields,
        },
    )
