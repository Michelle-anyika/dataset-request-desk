from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.catalog.import_service import ImportFailed
from apps.catalog.spreadsheet import export_lines
from apps.requests_desk.request_import import Action, import_requests


class Command(BaseCommand):
    help = (
        "Migrate requests from the operations spreadsheet (.csv or .xlsx). Previews unless --commit is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument("--as", dest="email", required=True, help="Admin recorded on the imported events")
        parser.add_argument(
            "--commit", action="store_true", help="Save the rows that pass (default: preview)"
        )

    def handle(self, *args, path, email, commit, **options):
        admin = get_user_model().objects.filter(email=email.lower(), is_active=True).first()
        if admin is None or admin.role != Role.ADMIN:
            raise CommandError(f"{email} must be an active admin account.")
        try:
            with path.open("rb") as file:
                report = import_requests(export_lines(file, path.name), admin=admin, commit=commit)
        except (OSError, ImportFailed) as exc:
            raise CommandError(str(exc)) from exc

        verb = "Created" if commit else "Preview: would create"
        self.stdout.write(
            f"{verb} {report.count(Action.CREATE)}, unchanged {report.count(Action.UNCHANGED)} "
            f"(imported before), skipped {report.count(Action.SKIP)}."
        )
        for row in report.rows:
            if row.action == Action.SKIP:
                self.stdout.write(
                    f"  row {row.row} ({row.reference or 'no reference'}): {row.reason_code}: {row.message}"
                )
        if not commit and report.count(Action.CREATE):
            self.stdout.write("Nothing was saved. Run again with --commit to import.")
