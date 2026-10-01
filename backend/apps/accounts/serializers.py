from django.contrib.auth import get_user_model
from rest_framework import serializers


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
