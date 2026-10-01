from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication

SESSION_VERSION_CLAIM = "sv"


class SessionRevoked(AuthenticationFailed):
    default_detail = "Your session has ended. Please log in again."
    default_code = "session_revoked"


class InvalidSession(AuthenticationFailed):
    default_detail = "Your session is not valid. Please log in again."
    default_code = "invalid_session"


def is_current_session(token, user) -> bool:
    """A token is only valid for the session version it was issued with."""
    return token.get(SESSION_VERSION_CLAIM) == user.session_version


class JWTAuthentication(BaseJWTAuthentication):
    """Bearer access tokens, checked against the database on every request.

    The base class already rejects unknown and inactive users; this adds session revocation. The role
    is read from the loaded user, never from the token, so a role change applies on the next request.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not is_current_session(validated_token, user):
            raise SessionRevoked()
        return user
