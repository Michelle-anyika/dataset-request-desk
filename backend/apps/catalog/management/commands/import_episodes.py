from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.catalog.import_service import ImportFailed, import_episodes
from apps.catalog.models import IssueSeverity


class Command(BaseCommand):
    help = "Import episodes from a recording-system CSV export. Safe to run repeatedly on the same file."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--as", dest="email", required=True, help="Operator or admin recorded as importer"
        )

    def handle(self, *args, path, email, **options):
        user = get_user_model().objects.filter(email=email.lower(), is_active=True).first()
        if user is None or user.role not in (Role.OPERATOR, Role.ADMIN):
            raise CommandError(f"{email} must be an active operator or admin account.")
        try:
            with path.open(encoding="utf-8-sig", newline="") as export:
                batch = import_episodes(export, file_name=path.name, uploaded_by=user)
        except (OSError, ImportFailed) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"{batch.total_rows} rows: {batch.created_count} created, {batch.updated_count} updated, "
            f"{batch.unchanged_count} unchanged, {batch.skipped_count} skipped "
            f"({batch.fixed_count} imported after fixes). Report: import #{batch.pk}."
        )
        for issue in batch.issues.filter(severity=IssueSeverity.SKIPPED):
            self.stdout.write(f"  line {issue.row_number:>4}  {issue.reason_code:<26} {issue.message}")
