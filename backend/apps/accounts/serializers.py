from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import Role
from apps.core.query import BooleanParam, QueryParamsSerializer


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.lower()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role", "organisation"]
        read_only_fields = fields


class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Bearer token, valid for 10 minutes. Keep it in memory only.")


class LoginResponseSerializer(AccessTokenSerializer):
    user = UserSerializer()


class ManagedUserSerializer(serializers.ModelSerializer):
    """What admins see about an account."""

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role", "organisation", "is_active", "last_login", "created_at"]
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    full_name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=Role.choices)
    organisation = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.lower()
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        # The password policy compares against the other fields (e.g. not similar to the email or name).
        candidate = get_user_model()(email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except Exception as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class UserUpdateSerializer(serializers.Serializer):
    """Fields an admin may change. The email is the login and stays fixed."""

    full_name = serializers.CharField(max_length=150, required=False)
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    organisation = serializers.CharField(max_length=150, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(max_length=128, write_only=True, required=False, trim_whitespace=False)

    def validate_password(self, value):
        try:
            validate_password(value, user=self.context["user"])
        except Exception as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class UserFilterSerializer(QueryParamsSerializer):
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    is_active = BooleanParam()
    search = serializers.CharField(max_length=100, required=False, help_text="Email or name contains.")
