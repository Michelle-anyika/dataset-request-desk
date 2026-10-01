"""Demo data for local development and review: the accounts from seed/users.json and the known robots."""

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import Role
from apps.catalog.models import KNOWN_ROBOTS, Robot

DEFAULT_USERS_FILE = Path(settings.BASE_DIR) / "seed" / "users.json"


@dataclass(frozen=True)
class SeedReport:
    users_created: int
    users_existing: int
    robots_created: int
    robots_existing: int


@transaction.atomic
def seed_demo_data(users_file: Path) -> SeedReport:
    """Create missing users and robots. Safe to run repeatedly: existing rows are never modified."""
    entries = json.loads(Path(users_file).read_text(encoding="utf-8"))
    User = get_user_model()

    users_created = 0
    for entry in entries:
        if entry["role"] not in Role.values:
            raise ValueError(f"Unknown role {entry['role']!r} for {entry['email']}")
        email = entry["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            continue  # keep any password or role changed since the first seed
        User.objects.create_user(
            email=email,
            password=entry["password"],
            full_name=entry["name"],
            organisation=entry.get("organisation", ""),
            role=entry["role"],
        )
        users_created += 1

    robots_created = 0
    for robot_id in KNOWN_ROBOTS:
        _, created = Robot.objects.get_or_create(id=robot_id, defaults={"kind": Robot.kind_from_id(robot_id)})
        robots_created += created

    return SeedReport(
        users_created=users_created,
        users_existing=len(entries) - users_created,
        robots_created=robots_created,
        robots_existing=len(KNOWN_ROBOTS) - robots_created,
    )
