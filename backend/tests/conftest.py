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
