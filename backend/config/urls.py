from django.urls import include, path

from apps.core.docs import SchemaView, SwaggerView
from apps.core.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.accounts.user_urls")),
    path("api/", include("apps.requests_desk.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/schema/", SchemaView.as_view(), name="api-schema"),
    path("api/docs/", SwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
