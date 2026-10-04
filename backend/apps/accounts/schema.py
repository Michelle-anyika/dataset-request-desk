from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class DeskJWTScheme(SimpleJWTScheme):
    """Documents our JWTAuthentication subclass as the standard bearer scheme."""

    target_class = "apps.accounts.authentication.JWTAuthentication"
