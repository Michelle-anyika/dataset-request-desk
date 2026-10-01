"""Request IDs and one structured access log line per request."""

import logging
import re
import time
import uuid

REQUEST_ID_HEADER = "X-Request-ID"

# Incoming IDs come from untrusted clients: accept only short, printable tokens (no log injection).
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

logger = logging.getLogger("desk.request")


class RequestLoggingMiddleware:
    """Must be first in MIDDLEWARE so the duration covers the whole stack."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = self._request_id(request)
        started = time.perf_counter()

        response = self.get_response(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response[REQUEST_ID_HEADER] = request.request_id
        # request.user is set by authentication further down the stack (absent for anonymous calls).
        user = getattr(request, "user", None)
        user_id = str(user.pk) if user is not None and user.is_authenticated else None

        logger.log(
            self._level(response.status_code),
            "%s %s %s",
            request.method,
            request.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "request_id": request.request_id,
            },
        )
        return response

    @staticmethod
    def _request_id(request) -> str:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        return incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex

    @staticmethod
    def _level(status: int) -> int:
        if status >= 500:
            return logging.ERROR
        if status >= 400:
            return logging.WARNING
        return logging.INFO


# API responses are JSON: they need nothing loaded and must never be framed.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"


class ContentSecurityPolicyMiddleware:
    """Adds the API's Content-Security-Policy unless a view set its own (the Swagger page does)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", API_CONTENT_SECURITY_POLICY)
        return response
