"""OpenAPI schema and Swagger UI, served only when API_DOCS_ENABLED is on (off by default in production)."""

from django.conf import settings
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny


class DocsEnabledMixin:
    authentication_classes = []
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        # Checked before DRF picks a renderer, so the 404 is our usual JSON error, not an OpenAPI document.
        if not settings.API_DOCS_ENABLED:
            return JsonResponse({"error": {"code": "not_found", "message": "Not found."}}, status=404)
        return super().dispatch(request, *args, **kwargs)


class SchemaView(DocsEnabledMixin, SpectacularAPIView):
    pass


# Development only (docs are off in production): Swagger UI loads its assets from jsDelivr and starts with an
# inline script.
DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SwaggerView(DocsEnabledMixin, SpectacularSwaggerView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Content-Security-Policy"] = DOCS_CONTENT_SECURITY_POLICY
        return response
