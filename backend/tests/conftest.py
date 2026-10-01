import pytest


@pytest.fixture(autouse=True)
def fast_password_hashing(request, settings):
    """PBKDF2 is deliberately slow; most tests don't care how passwords are hashed.

    Tests that check the production hasher opt out with ``@pytest.mark.real_password_hashing``.
    """
    if "real_password_hashing" not in request.keywords:
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
