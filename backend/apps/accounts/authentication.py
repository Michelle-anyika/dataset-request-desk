from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication


class SessionRevoked(AuthenticationFailed):
    default_detail = "Your session has ended. Please log in again."
    default_code = "session_revoked"


def issued_before_revocation(issued_at: int | None, user) -> bool:
    """True when a token predates the user's ``tokens_valid_after``.

    JWT ``iat`` has one-second precision, so the comparison is made in whole seconds: a token issued
    within the same second as a revocation is accepted, rather than rejecting a fresh login made
    straight after it.
    """
    return issued_at is None or int(issued_at) < int(user.tokens_valid_after.timestamp())


class JWTAuthentication(BaseJWTAuthentication):
    """Bearer access tokens, checked against the database on every request.

    The base class already rejects unknown and inactive users; this adds session revocation. The role
    is read from the loaded user, never from the token, so a role change applies on the next request.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if issued_before_revocation(validated_token.get("iat"), user):
            raise SessionRevoked()
        return user
