from django.urls import include, path

from apps.core.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
]
