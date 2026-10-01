import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.catalog.models import Robot
from apps.core.seed import DEFAULT_USERS_FILE, seed_demo_data

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_creates_the_seed_users_with_hashed_passwords():
    seed_demo_data(DEFAULT_USERS_FILE)

    assert User.objects.count() == 5
    admin = User.objects.get(email="admin@example.com")
    assert (admin.role, admin.full_name) == ("admin", "Ada Admin")
    assert admin.password != "admin123"
    assert admin.check_password("admin123")
    client = User.objects.get(email="client-a@example.com")
    assert (client.role, client.organisation) == ("client", "Acme Robotics")
    operators = set(User.objects.filter(role="operator").values_list("email", flat=True))
    assert operators == {"ops1@example.com", "ops2@example.com"}


def test_creates_the_known_robots():
    seed_demo_data(DEFAULT_USERS_FILE)

    assert list(Robot.objects.values_list("id", "kind")) == [
        ("arm-01", "arm"),
        ("arm-02", "arm"),
        ("arm-03", "arm"),
        ("humanoid-01", "humanoid"),
        ("mobile-01", "mobile"),
    ]


def test_running_twice_creates_nothing_new():
    first = seed_demo_data(DEFAULT_USERS_FILE)
    second = seed_demo_data(DEFAULT_USERS_FILE)

    assert (first.users_created, first.robots_created) == (5, 5)
    assert (second.users_created, second.robots_created) == (0, 0)
    assert (second.users_existing, second.robots_existing) == (5, 5)
    assert User.objects.count() == 5
    assert Robot.objects.count() == 5


def test_never_overwrites_an_existing_user():
    User.objects.create_user(
        email="admin@example.com", password="changed-later", full_name="Ada A.", role="admin"
    )

    report = seed_demo_data(DEFAULT_USERS_FILE)

    assert report.users_created == 4
    assert User.objects.get(email="admin@example.com").check_password("changed-later")


def test_invalid_file_creates_nothing(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps(
            [
                {"email": "ok@example.com", "password": "p", "role": "client", "name": "Fine"},
                {"email": "x@example.com", "password": "p", "role": "superhero", "name": "X"},
            ]
        )
    )

    with pytest.raises(ValueError, match="superhero"):
        seed_demo_data(users_file)
    assert User.objects.count() == 0


def test_command_reports_what_it_did():
    out = StringIO()

    call_command("seed", stdout=out)

    assert "Users: 5 created, 0 already present" in out.getvalue()
    assert "Robots: 5 created, 0 already present" in out.getvalue()
