import logging

from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services, sessions, throttling
from apps.accounts.audit import email_hash, security_event
from apps.accounts.authentication import SessionReuseDetected
from apps.accounts.serializers import (
    AccessTokenSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    ManagedUserSerializer,
    UserCreateSerializer,
    UserFilterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.core.openapi import error_response
from apps.core.permissions import IsAdmin


class InvalidCredentials(AuthenticationFailed):
    # One message for unknown emails, wrong passwords and inactive accounts: nothing to learn from the answer.
    default_detail = "Email or password is incorrect."
    default_code = "invalid_credentials"


class CrossSiteRequest(PermissionDenied):
    default_detail = "Requests from other sites are not allowed."
    default_code = "cross_site_request"


CROSS_SITE = error_response("The browser marked the request as coming from another site.")


class PublicAuthView(APIView):
    """Auth endpoints that work without an access token (they rely on credentials or the refresh cookie).

    Because the refresh cookie is sent automatically, these endpoints are the CSRF surface. Besides the
    cookie's SameSite=Strict, they refuse any request the browser marks as started by another site.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            raise CrossSiteRequest()
        super().initial(request, *args, **kwargs)

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
        responses={
            200: LoginResponseSerializer,
            401: error_response("Email or password is incorrect."),
            403: CROSS_SITE,
        },
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
        responses={
            200: AccessTokenSerializer,
            401: error_response("No session, or it has expired or been revoked."),
            403: CROSS_SITE,
        },
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
        request=None,
        responses={204: None, 403: CROSS_SITE},
        description="Ends this session and clears the cookie.",
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


class UserViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Admin user management. Accounts are deactivated, never deleted."""

    permission_classes = [*viewsets.GenericViewSet.permission_classes, IsAdmin]
    serializer_class = ManagedUserSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = get_user_model().objects.order_by("email")
        if self.action != "list":
            return queryset
        filters = UserFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        if "role" in params:
            queryset = queryset.filter(role=params["role"])
        if "is_active" in params:
            queryset = queryset.filter(is_active=params["is_active"] == "true")
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(Q(email__icontains=term) | Q(full_name__icontains=term))
        return queryset

    @extend_schema(parameters=[UserFilterSerializer])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=UserCreateSerializer, responses={201: ManagedUserSerializer})
    def create(self, request):
        payload = UserCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = services.create_user(**payload.validated_data)
        security_event(
            "admin.user_created", request, user_id=str(request.user.pk), target_user_id=str(user.pk)
        )
        return Response(ManagedUserSerializer(user).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=UserUpdateSerializer,
        responses={
            200: ManagedUserSerializer,
            409: error_response("You can't demote or deactivate yourself, or the last active admin."),
        },
    )
    def partial_update(self, request, pk=None):
        user = self.get_object()
        payload = UserUpdateSerializer(data=request.data, context={"user": user})
        payload.is_valid(raise_exception=True)
        changed = services.update_user(user, actor=request.user, **payload.validated_data)
        if changed:
            security_event(
                "admin.user_updated",
                request,
                user_id=str(request.user.pk),
                target_user_id=str(user.pk),
                changed_fields=changed,
            )
        user.refresh_from_db()
        return Response(ManagedUserSerializer(user).data)
