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
