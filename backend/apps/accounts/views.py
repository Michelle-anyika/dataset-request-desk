from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import LoginSerializer, UserSerializer
from apps.accounts.sessions import start_session


class InvalidCredentials(AuthenticationFailed):
    # One message for unknown emails, wrong passwords and inactive accounts: nothing to learn from the answer.
    default_detail = "Email or password is incorrect."
    default_code = "invalid_credentials"


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        # Without an authenticator DRF would turn 401 into 403; credentials errors are 401 with a challenge.
        return 'Bearer realm="api"'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Django's backend also hashes for unknown emails, so timing doesn't reveal which accounts exist,
        # and it refuses inactive users.
        credentials = serializer.validated_data
        user = authenticate(request, email=credentials["email"], password=credentials["password"])
        if user is None:
            raise InvalidCredentials()

        response = Response({"user": UserSerializer(user).data})
        response.data["access"] = start_session(user, response)
        return response


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)
