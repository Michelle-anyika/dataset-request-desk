"""Migrate the requests tracked in the operations spreadsheet (issue #37, PLAN.md §8.1).

An admin previews the file first: every row says what would happen, and nothing is saved. Committing does the
same checks and saves the rows that pass. Rows are matched on the spreadsheet's reference, so running the same
file again creates nothing. Problems are reported per row, never guessed: an unknown client, a status the
workflow can't start from, a count or a date that doesn't parse.

Each imported request gets one status event, "imported", by the admin who ran it. Imports notify nobody: these
are existing requests, already known to everyone involved.
"""

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.analytics.cache import bump_data_version
from apps.catalog.import_service import ImportFailed
from apps.catalog.normalise import normalise_task_name
from apps.requests_desk.models import DatasetRequest, RequestStatus, RequestStatusEvent
from apps.requests_desk.serializers import MAX_EPISODES_PER_REQUEST

COLUMNS = ["reference", "client_email", "task_name", "episodes_requested", "deadline", "notes", "status"]
# Delivered needs its episodes assigned here first (the workflow's guard), so it isn't one of these.
IMPORTABLE = {
    RequestStatus.SUBMITTED,
    RequestStatus.IN_PROGRESS,
    RequestStatus.ACCEPTED,
    RequestStatus.REJECTED,
}
_LOCK = 7_310_002  # pg advisory lock key: one migration commit at a time


class Action:
    CREATE = "create"
    UNCHANGED = "unchanged"  # already imported earlier: matched on the reference, left as it is now
    SKIP = "skip"


@dataclass
class RowResult:
    row: int
    reference: str
    action: str
    reason_code: str = ""
    message: str = ""
    client_email: str = ""
    task_name: str = ""
    status: str = ""


@dataclass
class Report:
    rows: list[RowResult] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for row in self.rows if row.action == action)

    def as_dict(self) -> dict:
        return {
            "create": self.count(Action.CREATE),
            "unchanged": self.count(Action.UNCHANGED),
            "skip": self.count(Action.SKIP),
            "rows": [asdict(row) for row in self.rows],
        }


class _Skip(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _Planned:
    result: RowResult
    client: object = None
    episodes_requested: int = 0
    deadline: date | None = None
    notes: str = ""


def import_requests(lines: Iterable[str], *, admin, commit: bool) -> Report:
    """Check every row; with ``commit``, also save the ones that pass. Returns what happened to each row."""
    reader = csv.DictReader(lines)
    try:
        _check_header(reader.fieldnames)
        reader.fieldnames = [name.strip().lower() if name else name for name in reader.fieldnames]
        if not commit:
            return Report([planned.result for planned in _plan(reader)])
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK])
            plan = _plan(reader)  # under the lock, so "already imported" is decided against committed data
            _save([planned for planned in plan if planned.result.action == Action.CREATE], admin)
    except UnicodeDecodeError as exc:
        raise ImportFailed("The file is not UTF-8 text. Export it as CSV with UTF-8 encoding.") from exc
    except csv.Error as exc:
        raise ImportFailed(
            "The file is not valid CSV. Export it again as CSV (comma-separated, UTF-8)."
        ) from exc
    if any(planned.result.action == Action.CREATE for planned in plan):
        bump_data_version()  # after commit: request analytics have changed
    return Report([planned.result for planned in plan])


def _check_header(fieldnames) -> None:
    if not fieldnames:
        raise ImportFailed("The file is empty.")
    present = {name.strip().lower() for name in fieldnames if name}
    missing = [column for column in COLUMNS if column not in present]
    if missing:
        raise ImportFailed(f"Missing required columns: {', '.join(missing)}.")


def _plan(reader: csv.DictReader) -> list[_Planned]:
    rows = [(reader.line_num, raw) for raw in reader]
    references = {(raw.get("reference") or "").strip() for _, raw in rows}
    emails = {(raw.get("client_email") or "").strip().lower() for _, raw in rows}
    # Two queries for the whole file, however long it is.
    existing = set(
        DatasetRequest.objects.filter(spreadsheet_ref__in=references - {""}).values_list(
            "spreadsheet_ref", flat=True
        )
    )
    users = {user.email: user for user in get_user_model().objects.filter(email__in=emails - {""})}

    plan: list[_Planned] = []
    seen: dict[str, int] = {}
    for line, raw in rows:
        reference = (raw.get("reference") or "").strip()
        result = RowResult(row=line, reference=reference, action=Action.SKIP)
        try:
            planned = _check_row(raw, result, users)
            if reference in seen:
                raise _Skip(
                    "duplicate_reference", f"Same reference as row {seen[reference]}, which was used."
                )
            seen[reference] = line
            result.action = Action.UNCHANGED if reference in existing else Action.CREATE
        except _Skip as skip:
            result.action, result.reason_code, result.message = Action.SKIP, skip.code, skip.message
            planned = _Planned(result)
        plan.append(planned)
    return plan


def _check_row(raw: dict, result: RowResult, users: dict) -> _Planned:
    if None in raw or any(raw.get(column) is None for column in COLUMNS):
        raise _Skip("malformed_row", f"Expected {len(COLUMNS)} columns.")
    if not result.reference:
        raise _Skip(
            "missing_reference", "Every row needs the spreadsheet's reference, so re-runs can't duplicate."
        )
    if len(result.reference) > 64:
        raise _Skip("invalid_reference", "The reference is longer than 64 characters.")

    result.client_email = raw["client_email"].strip().lower()
    client = users.get(result.client_email)
    if client is None:
        raise _Skip(
            "unknown_client", f"No account for {result.client_email or 'an empty email'}. Create it first."
        )
    if client.role != Role.CLIENT:
        raise _Skip("not_a_client", f"{result.client_email} is not a client account.")

    result.task_name = normalise_task_name(raw["task_name"])
    if not result.task_name:
        raise _Skip("missing_task_name", "The task is empty.")
    if len(result.task_name) > 120:
        raise _Skip("invalid_task_name", "The task is longer than 120 characters.")

    episodes = raw["episodes_requested"].strip()
    if not (episodes.isascii() and episodes.isdigit() and 1 <= int(episodes) <= MAX_EPISODES_PER_REQUEST):
        raise _Skip(
            "invalid_episodes_requested",
            f"Episodes requested must be a whole number from 1 to {MAX_EPISODES_PER_REQUEST:,}.",
        )

    deadline = _deadline(raw["deadline"].strip())

    notes = raw["notes"].strip()
    if len(notes) > 2000:
        raise _Skip("invalid_notes", "The notes are longer than 2,000 characters.")

    result.status = raw["status"].strip().lower().replace(" ", "_").replace("-", "_")
    if result.status == RequestStatus.DELIVERED:
        raise _Skip(
            "delivered_needs_episodes",
            "A delivered request needs its episodes assigned here before it can be delivered. Import it as "
            "in_progress and assign them, or let the client decide in the spreadsheet first.",
        )
    if result.status not in IMPORTABLE:
        raise _Skip("invalid_status", f"Unknown status. Use one of: {', '.join(sorted(IMPORTABLE))}.")

    return _Planned(result, client=client, episodes_requested=int(episodes), deadline=deadline, notes=notes)


def _deadline(value: str) -> date:
    # The spreadsheet's dates as typed (2026-11-01) or as Excel exports them (2026-11-01T00:00:00).
    # Past deadlines are kept: these are existing requests, some long finished.
    try:
        return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)
    except ValueError as exc:
        raise _Skip("invalid_deadline", "The deadline must be a date like 2026-11-01.") from exc


def _save(rows: list[_Planned], admin) -> None:
    """Two bulk inserts for the whole file: ids are UUIDs made here, so events can point at their requests."""
    now = timezone.now()
    requests = [
        DatasetRequest(
            client=planned.client,
            task_name=planned.result.task_name,
            episodes_requested=planned.episodes_requested,
            deadline=planned.deadline,
            notes=planned.notes,
            status=planned.result.status,
            status_changed_at=now,
            spreadsheet_ref=planned.result.reference,
        )
        for planned in rows
    ]
    DatasetRequest.objects.bulk_create(requests, batch_size=1000)
    RequestStatusEvent.objects.bulk_create(
        [
            RequestStatusEvent(
                request=request,
                from_status=None,
                to_status=planned.result.status,
                changed_by=admin,
                changed_at=now,
                comment=f"Imported from the spreadsheet (reference {planned.result.reference}, "
                f"row {planned.result.row}).",
            )
            for request, planned in zip(requests, rows, strict=True)
        ],
        batch_size=1000,
    )
