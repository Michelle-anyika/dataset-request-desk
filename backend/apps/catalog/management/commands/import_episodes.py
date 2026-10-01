import hashlib
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.catalog.import_service import ImportFailed, import_episodes
from apps.catalog.models import ImportBatch, ImportStatus, IssueSeverity


def _open_export(path: Path):
    # Same decoding as the upload endpoint: drop a byte-order mark, let the csv module see CRLF.
    return path.open(encoding="utf-8-sig", newline="")


def _digest(path: Path) -> str:
    """SHA-256 computed exactly as the import service computes it, over the decoded lines."""
    hasher = hashlib.sha256()
    with _open_export(path) as export:
        for line in export:
            hasher.update(line.encode())
    return hasher.hexdigest()


class Command(BaseCommand):
    help = "Import episodes from a recording-system CSV export. Safe to run repeatedly on the same file."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--as", dest="email", required=True, help="Operator or admin recorded as importer"
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Do nothing if this exact file was already imported successfully (used for demo seeding).",
        )

    def handle(self, *args, path, email, once, **options):
        user = get_user_model().objects.filter(email=email.lower(), is_active=True).first()
        if user is None or user.role not in (Role.OPERATOR, Role.ADMIN):
            raise CommandError(f"{email} must be an active operator or admin account.")
        try:
            if once:
                earlier = ImportBatch.objects.filter(file_sha256=_digest(path), status=ImportStatus.COMPLETED)
                if earlier.exists():
                    self.stdout.write(f"{path.name} was already imported (import #{earlier.first().pk}).")
                    return
            with _open_export(path) as export:
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
