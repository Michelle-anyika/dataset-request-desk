"""Login sessions: a short-lived access token returned to the client and a refresh token kept in a cookie."""

from django.conf import settings
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.tokens import RefreshToken

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth/"  # the browser only sends it to the auth endpoints


def start_session(user, response) -> str:
    """Issue a new token pair: the refresh token goes into the cookie, the access token is returned."""
    refresh = RefreshToken.for_user(user)  # also recorded as an outstanding token, so it can be revoked
    set_refresh_cookie(response, str(refresh))
    update_last_login(None, user)
    return str(refresh.access_token)


def set_refresh_cookie(response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,  # unreadable by JavaScript, so an injected script can't steal it
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="Strict",  # never sent with requests started by another site
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, samesite="Strict")
