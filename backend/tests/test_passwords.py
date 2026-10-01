import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from tests.conftest import DEFAULT_PASSWORD
from tests.test_auth_login import login

pytestmark = [pytest.mark.django_db, pytest.mark.real_password_hashing]


def test_new_passwords_are_hashed_with_argon2id(make_user):
    user = make_user(email="a@example.com")

    assert user.password.startswith("argon2$argon2id$")


def test_an_older_pbkdf2_hash_is_upgraded_on_the_next_login(api_client, make_user):
    user = make_user(email="a@example.com")
    user.password = make_password(DEFAULT_PASSWORD, hasher="pbkdf2_sha256")
    user.save()

    assert login(api_client, "a@example.com").status_code == 200

    user.refresh_from_db()
    assert user.password.startswith("argon2$argon2id$")


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Sh0rt-pass", "too short"),
        ("123456789012", "entirely numeric"),
        ("password1234", "too common"),
        ("ada.lovelace.home", "too similar"),
    ],
)
def test_weak_passwords_are_rejected(make_user, password, reason):
    user = make_user(email="ada.lovelace@example.com", full_name="Ada Lovelace")

    with pytest.raises(ValidationError, match=reason):
        validate_password(password, user=user)


def test_a_long_passphrase_is_accepted(make_user):
    user = make_user(email="ada.lovelace@example.com", full_name="Ada Lovelace")

    validate_password("violet tractor under the bridge", user=user)
