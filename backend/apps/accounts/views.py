from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import sessions, throttling
from apps.accounts.serializers import LoginSerializer, UserSerializer


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

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email, password = serializer.validated_data["email"], serializer.validated_data["password"]

        wait = throttling.lockout_seconds(email)
        if wait is not None:
            raise Throttled(wait=wait)

        # Django's backend also hashes for unknown emails, so timing doesn't reveal which accounts exist,
        # and it refuses inactive users.
        user = authenticate(request, email=email, password=password)
        if user is None:
            throttling.record_failure(email)
            raise InvalidCredentials()
        throttling.clear_failures(email)

        response = Response({"user": UserSerializer(user).data})
        response.data["access"] = sessions.start_session(user, response)
        return response


class RefreshView(PublicAuthView):
    def post(self, request):
        raw_refresh = request.COOKIES.get(sessions.REFRESH_COOKIE)
        if not raw_refresh:
            raise NotAuthenticated("No active session.")
        try:
            access, refresh = sessions.rotate_session(raw_refresh)
        except AuthenticationFailed as exc:
            response = self.handle_exception(exc)
            sessions.clear_refresh_cookie(response)
            return response

        response = Response({"access": access})
        sessions.set_refresh_cookie(response, refresh)
        return response


class LogoutView(PublicAuthView):
    def post(self, request):
        raw_refresh = request.COOKIES.get(sessions.REFRESH_COOKIE)
        if raw_refresh:
            sessions.end_session(raw_refresh)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        sessions.clear_refresh_cookie(response)
        return response


class LogoutAllView(APIView):
    def post(self, request):
        sessions.revoke_all_sessions(request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        sessions.clear_refresh_cookie(response)
        return response


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)
