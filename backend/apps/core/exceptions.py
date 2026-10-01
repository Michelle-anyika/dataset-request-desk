"""One error shape for every API error: ``{"error": {"code", "message", "details"?}}``."""

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unexpected error: Django returns a generic 500 and logs it with the traceback

    detail = getattr(exc, "detail", None)
    if isinstance(exc, ValidationError):
        error = {"code": "invalid", "message": "Some fields are invalid.", "details": detail}
    elif isinstance(detail, dict) and "detail" in detail:
        # SimpleJWT nests its own detail/code pair.
        error = {"code": str(detail.get("code", exc.default_code)), "message": str(detail["detail"])}
    else:
        error = {"code": getattr(detail, "code", None) or exc.default_code, "message": str(detail)}

    response.data = {"error": error}
    return response
