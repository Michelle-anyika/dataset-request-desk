import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

DEFAULT_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def fast_password_hashing(request, settings):
    """PBKDF2 and Argon2 are deliberately slow; most tests don't care how passwords are hashed.

    Tests that check the production hashers opt out with ``@pytest.mark.real_password_hashing``.
    """
    if "real_password_hashing" not in request.keywords:
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    def make(email="user@example.com", role="client", password=DEFAULT_PASSWORD, **fields):
        fields.setdefault("full_name", email.split("@")[0].title())
        return get_user_model().objects.create_user(email=email, password=password, role=role, **fields)

    return make


@pytest.fixture
def api_as(make_user):
    """An API client authenticated as a new user with the given role.

    Skips the login flow, which is covered by the test_auth_* modules.
    """

    def as_role(role="client", **fields):
        fields.setdefault("email", f"{role}-{get_user_model().objects.count() + 1}@example.com")
        user = make_user(role=role, **fields)
        client = APIClient()
        client.force_authenticate(user)
        client.user = user
        return client

    return as_role
