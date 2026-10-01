import logging

from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import sessions, throttling
from apps.accounts.audit import email_hash, security_event
from apps.accounts.authentication import SessionReuseDetected
from apps.accounts.serializers import (
    AccessTokenSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    UserSerializer,
)


class InvalidCredentials(AuthenticationFailed):
    # One message for unknown emails, wrong passwords and inactive accounts: nothing to learn from the answer.
    default_detail = "Email or password is incorrect."
    default_code = "invalid_credentials"


class PublicAuthView(APIView):
    """Auth endpoints that work without an access token (they rely on credentials or the refresh cookie)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        # Without an authenticator DRF would turn 401 into 403; credentials errors are 401 with a challenge.
        return 'Bearer realm="api"'


class LoginView(PublicAuthView):
    throttle_classes = [throttling.LoginRateThrottle]

    def throttled(self, request, wait):
        security_event("auth.throttled", request, level=logging.WARNING, limit="ip")
        super().throttled(request, wait)

    @extend_schema(
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
        description="Sets the refresh token as an HttpOnly cookie. Throttled per IP and per email.",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email, password = serializer.validated_data["email"], serializer.validated_data["password"]

        wait = throttling.lockout_seconds(email)
        if wait is not None:
            security_event(
                "auth.throttled", request, level=logging.WARNING, limit="email", email_hash=email_hash(email)
            )
            raise Throttled(wait=wait)

        # Django's backend also hashes for unknown emails, so timing doesn't reveal which accounts exist,
        # and it refuses inactive users.
        user = authenticate(request, email=email, password=password)
        if user is None:
            throttling.record_failure(email)
            security_event("auth.login_failed", request, level=logging.WARNING, email_hash=email_hash(email))
            raise InvalidCredentials()
        throttling.clear_failures(email)
        security_event("auth.login_succeeded", request, user_id=str(user.pk))

        response = Response({"user": UserSerializer(user).data})
        response.data["access"] = sessions.start_session(user, response)
        return response


class RefreshView(PublicAuthView):
    @extend_schema(
        request=None,
        responses={200: AccessTokenSerializer},
        description="Uses and rotates the refresh cookie. Reusing an old refresh token ends every session.",
    )
    def post(self, request):
        raw_refresh = request.COOKIES.get(sessions.REFRESH_COOKIE)
        if not raw_refresh:
            raise NotAuthenticated("No active session.")
        try:
            access, refresh = sessions.rotate_session(raw_refresh)
        except AuthenticationFailed as exc:
            if isinstance(exc, SessionReuseDetected):
                security_event(
                    "auth.refresh_reuse_detected", request, level=logging.ERROR, user_id=exc.user_id
                )
            response = self.handle_exception(exc)
            sessions.clear_refresh_cookie(response)
            return response

        response = Response({"access": access})
        sessions.set_refresh_cookie(response, refresh)
        return response


class LogoutView(PublicAuthView):
    @extend_schema(
        request=None, responses={204: None}, description="Ends this session and clears the cookie."
    )
    def post(self, request):
        raw_refresh = request.COOKIES.get(sessions.REFRESH_COOKIE)
        if raw_refresh and (user_id := sessions.end_session(raw_refresh)):
            security_event("auth.logout", request, user_id=user_id)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        sessions.clear_refresh_cookie(response)
        return response


class LogoutAllView(APIView):
    @extend_schema(request=None, responses={204: None}, description="Ends every session of the current user.")
    def post(self, request):
        sessions.revoke_all_sessions(request.user)
        security_event("auth.logout_all", request, user_id=str(request.user.pk))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        sessions.clear_refresh_cookie(response)
        return response


class MeView(APIView):
    @extend_schema(responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)
