import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def health(request):
    """Liveness and database check for load balancers and uptime monitors. No authentication."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("Health check failed: database unavailable")
        return JsonResponse({"status": "error", "db": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})


# Errors raised outside the API views (no matching URL, a request Django refuses, a crash) use the API's error
# shape too, instead of Django's HTML pages (config/urls.py). Never any detail: a 500 is logged with its
# traceback and reported to Sentry, not shown to the caller.
def _error(status, code, message):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def bad_request(request, exception):
    return _error(400, "bad_request", "Bad request.")


def permission_denied(request, exception):
    return _error(403, "permission_denied", "You do not have permission to perform this action.")


def not_found(request, exception):
    return _error(404, "not_found", "Not found.")


def server_error(request):
    return _error(500, "server_error", "Something went wrong on our side.")
