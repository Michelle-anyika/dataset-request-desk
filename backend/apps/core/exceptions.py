"""One error shape for every API error: ``{"error": {"code", "message", "details"?}}``."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    # Django's own exceptions carry no DRF error code; convert them as DRF does internally.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None  # unexpected error: Django returns a generic 500 and logs it with the traceback

    detail = getattr(exc, "detail", None)
    if isinstance(exc, exceptions.ValidationError):
        error = {"code": "invalid", "message": "Some fields are invalid.", "details": detail}
    elif isinstance(detail, dict) and "detail" in detail:
        # SimpleJWT nests its own detail/code pair.
        error = {"code": str(detail.get("code", exc.default_code)), "message": str(detail["detail"])}
    else:
        error = {"code": getattr(detail, "code", None) or exc.default_code, "message": str(detail)}
        if getattr(exc, "details", None):
            error["details"] = exc.details

    response.data = {"error": error}
    return response
