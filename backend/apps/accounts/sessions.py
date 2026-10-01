"""Login sessions: a short-lived access token returned to the client and a refresh token kept in a cookie.

Design and threat model: docs/security.md §3.
"""

from contextlib import suppress
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import (
    SESSION_VERSION_CLAIM,
    InvalidSession,
    SessionReuseDetected,
    SessionRevoked,
)

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth/"  # the browser only sends it to the auth endpoints

# Two tabs refreshing at the same moment both send the old cookie. A reuse this soon after rotation is a race,
# not a theft, so it is refused without ending the session.
REUSE_GRACE_PERIOD = timedelta(seconds=10)


def issue_tokens(user) -> tuple[str, str]:
    """Return a new (access, refresh) pair for the user's current session version."""
    refresh = RefreshToken.for_user(user)  # also recorded as an outstanding token, so it can be revoked
    refresh[SESSION_VERSION_CLAIM] = user.session_version  # copied into the access token below
    return str(refresh.access_token), str(refresh)


def start_session(user, response) -> str:
    """Log the user in: the refresh token goes into the cookie, the access token is returned."""
    access, refresh = issue_tokens(user)
    set_refresh_cookie(response, refresh)
    update_last_login(None, user)
    return access


def rotate_session(raw_refresh: str) -> tuple[str, str]:
    """Exchange a refresh token for a new pair, blacklisting the old one.

    A refresh token that was already rotated and is presented again means someone else has a copy:
    every session of that user is revoked.
    """
    try:
        payload = token_backend.decode(raw_refresh, verify=True)  # signature and expiry, not the blacklist
    except TokenBackendError as exc:
        raise InvalidSession() from exc
    if payload.get(api_settings.TOKEN_TYPE_CLAIM) != "refresh":
        raise InvalidSession()

    user = get_user_model().objects.filter(pk=payload.get(api_settings.USER_ID_CLAIM), is_active=True).first()
    if user is None or payload.get(SESSION_VERSION_CLAIM) != user.session_version:
        raise SessionRevoked()

    with transaction.atomic():
        # The row lock serialises concurrent refreshes of the same token, so it can only be rotated once.
        # order_by() drops SimpleJWT's default ordering by user, a join Postgres can't lock through.
        outstanding = (
            OutstandingToken.objects.select_for_update(of=("self",))
            .filter(jti=payload[api_settings.JTI_CLAIM])
            .order_by()
            .first()
        )
        if outstanding is None:
            raise InvalidSession()
        revoked = BlacklistedToken.objects.filter(token=outstanding).first()
        if revoked is None:
            BlacklistedToken.objects.create(token=outstanding)
            return issue_tokens(user)

    # Already rotated. Handled outside the transaction above so the revocation is committed, not rolled back.
    if revoked.blacklisted_at >= timezone.now() - REUSE_GRACE_PERIOD:
        raise InvalidSession()
    revoke_all_sessions(user)
    raise SessionReuseDetected(user.pk)


def end_session(raw_refresh: str) -> str | None:
    """Blacklist one session's refresh token and return its user id.

    An invalid or expired token has nothing left to end, so it returns None.
    """
    with suppress(TokenError):
        token = RefreshToken(raw_refresh)
        token.blacklist()
        return str(token[api_settings.USER_ID_CLAIM])
    return None


@transaction.atomic
def revoke_all_sessions(user) -> None:
    """End every session of the user at once, access tokens included."""
    get_user_model().objects.filter(pk=user.pk).update(session_version=F("session_version") + 1)
    user.refresh_from_db(fields=["session_version"])
    live = OutstandingToken.objects.filter(
        user=user, expires_at__gt=timezone.now(), blacklistedtoken__isnull=True
    )
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in live], ignore_conflicts=True
    )


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
