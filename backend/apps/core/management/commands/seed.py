from pathlib import Path

from django.core.management.base import BaseCommand

from apps.core.seed import DEFAULT_USERS_FILE, seed_demo_data


class Command(BaseCommand):
    help = "Create the demo accounts and known robots. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--users-file", type=Path, default=DEFAULT_USERS_FILE)

    def handle(self, *args, users_file, **options):
        r = seed_demo_data(users_file)
        self.stdout.write(f"Users: {r.users_created} created, {r.users_existing} already present")
        self.stdout.write(f"Robots: {r.robots_created} created, {r.robots_existing} already present")
