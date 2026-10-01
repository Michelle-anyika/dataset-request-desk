import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.accounts.models import Role

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_email_is_the_login_and_ids_are_uuids():
    user = User.objects.create_user(email="ops@example.com", password="s3cret-pass", full_name="Olu Operator")

    assert User.USERNAME_FIELD == "email"
    assert isinstance(user.pk, uuid.UUID)


def test_password_is_stored_hashed():
    user = User.objects.create_user(email="ops@example.com", password="s3cret-pass", full_name="Olu Operator")

    assert user.password != "s3cret-pass"
    assert user.password.startswith("pbkdf2_sha256$")
    assert user.check_password("s3cret-pass")


def test_email_is_normalised_to_lower_case():
    user = User.objects.create_user(email="  Ops@Example.COM ", password="x", full_name="Olu Operator")

    assert user.email == "ops@example.com"


def test_email_is_unique_regardless_of_case():
    User.objects.create_user(email="ops@example.com", password="x", full_name="Olu Operator")

    with pytest.raises(IntegrityError):
        User.objects.create(email="OPS@example.com", full_name="Duplicate")


def test_email_is_required():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="", password="x", full_name="No Email")


def test_new_users_are_active_clients_by_default():
    user = User.objects.create_user(email="client@example.com", password="x", full_name="Acme Robotics")

    assert user.role == Role.CLIENT
    assert user.is_active is True


def test_database_rejects_unknown_roles():
    with pytest.raises(IntegrityError):
        User.objects.create(email="x@example.com", full_name="X", role="superhero")


def test_superuser_is_an_admin():
    user = User.objects.create_superuser(email="admin@example.com", password="x", full_name="Ada Admin")

    assert user.role == Role.ADMIN
