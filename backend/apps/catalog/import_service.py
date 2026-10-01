"""Import episodes from the recording system's CSV export (PLAN.md §8).

Safe to run any number of times on the same file: rows are upserted on ``episode_id``, so a re-run reports
``0 created, N unchanged``. Every skipped or normalised row is recorded with its line number and reason.
Both the ``import_episodes`` command and the upload endpoint call ``import_episodes``.
"""

import csv
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.importing import COLUMNS, ParsedRow, RowRejected, parse_row
from apps.catalog.models import (
    Episode,
    ImportBatch,
    ImportRowIssue,
    ImportStatus,
    IssueSeverity,
    Quality,
    Robot,
)

# Fields written when an existing episode changes. bulk_update skips auto_now: updated_at is set by hand.
UPDATED_FIELDS = [
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
    "import_batch",
    "updated_at",
]
CHUNK_SIZE = 2000  # rows compared with the database per query; keeps memory and query size bounded
_IMPORT_LOCK = 7_310_001  # pg advisory lock key: one import at a time, so concurrent runs can't interleave


class ImportFailed(Exception):
    """The file as a whole can't be imported (for example, a required column is missing)."""


@dataclass
class _Row:
    line: int
    raw: dict
    parsed: ParsedRow


def import_episodes(lines: Iterable[str], *, file_name: str, uploaded_by) -> ImportBatch:
    """Import a CSV export. ``lines`` is any iterable of text lines (an open file, an upload, a StringIO)."""
    hasher = hashlib.sha256()

    def hashing(source):
        for line in source:
            hasher.update(line.encode())
            yield line

    batch = ImportBatch.objects.create(file_name=file_name[:255], file_sha256="", uploaded_by=uploaded_by)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_IMPORT_LOCK])
            _run(batch, csv.DictReader(hashing(lines)))
            batch.file_sha256 = hasher.hexdigest()
            batch.status = ImportStatus.COMPLETED
            batch.finished_at = timezone.now()
            batch.save()
    except ImportFailed as exc:
        # Recorded outside the rolled-back transaction, so the failed attempt stays in the history.
        batch.file_sha256 = hasher.hexdigest()
        batch.status = ImportStatus.FAILED
        batch.error_message = str(exc)
        batch.finished_at = timezone.now()
        batch.save()
        raise
    return batch


def _run(batch: ImportBatch, reader: csv.DictReader) -> None:
    _check_header(reader.fieldnames)
    # Read rows by normalised names, so a header like " Episode_ID" works the same as "episode_id".
    reader.fieldnames = [name.strip().lower() if name else name for name in reader.fieldnames]
    known_robots = set(Robot.objects.filter(is_active=True).values_list("id", flat=True))
    now = timezone.now()
    issues: list[ImportRowIssue] = []
    rows: dict[str, _Row] = {}  # first occurrence of each episode id in the file

    for raw in reader:
        line = reader.line_num
        batch.total_rows += 1
        if _is_blank(raw):
            issues.append(
                _issue(batch, line, raw, "", IssueSeverity.SKIPPED, "blank_line", "The line is empty.")
            )
            continue
        try:
            parsed = parse_row(raw, known_robots=known_robots, now=now)
        except RowRejected as rejected:
            episode_id = (raw.get("episode_id") or "").strip()
            issues.append(
                _issue(batch, line, raw, episode_id, IssueSeverity.SKIPPED, rejected.code, rejected.message)
            )
            continue

        first = rows.get(parsed.episode_id)
        if first is not None:
            same = first.parsed.values() == parsed.values()
            code = "duplicate_in_file" if same else "conflicting_duplicate"
            message = (
                f"Same episode as line {first.line}."
                if same
                else f"Differs from line {first.line}, which has the same episode id and was kept."
            )
            issues.append(_issue(batch, line, raw, parsed.episode_id, IssueSeverity.SKIPPED, code, message))
            continue
        rows[parsed.episode_id] = _Row(line, raw, parsed)

    ordered = list(rows.values())
    for start in range(0, len(ordered), CHUNK_SIZE):
        _store(batch, ordered[start : start + CHUNK_SIZE], issues)

    batch.skipped_count = sum(1 for issue in issues if issue.severity == IssueSeverity.SKIPPED)
    issues.sort(key=lambda issue: issue.row_number)  # fixes are added after the skips; report in file order
    ImportRowIssue.objects.bulk_create(issues, batch_size=1000)


def _store(batch: ImportBatch, chunk: list[_Row], issues: list[ImportRowIssue]) -> None:
    from apps.requests_desk.models import Assignment  # requests depend on episodes, not the other way round

    ids = [row.parsed.episode_id for row in chunk]
    existing = {episode.episode_id: episode for episode in Episode.objects.filter(episode_id__in=ids)}
    assigned = set(
        Assignment.objects.filter(episode__episode_id__in=ids, released_at__isnull=True).values_list(
            "episode__episode_id", flat=True
        )
    )
    to_create, to_update = [], []
    now = timezone.now()

    for row in chunk:
        values = row.parsed.values()
        episode = existing.get(row.parsed.episode_id)
        if episode is None:
            to_create.append(Episode(episode_id=row.parsed.episode_id, import_batch=batch, **values))
            batch.created_count += 1
        elif all(getattr(episode, field) == value for field, value in values.items()):
            batch.unchanged_count += 1
        elif row.parsed.episode_id in assigned and values["quality"] == Quality.BAD:
            # A delivered or in-progress request must not end up holding a bad episode.
            issues.append(
                _issue(
                    batch,
                    row.line,
                    row.raw,
                    row.parsed.episode_id,
                    IssueSeverity.SKIPPED,
                    "assigned_episode_conflict",
                    "The episode is assigned to a request and can't be changed to bad; unassign it first.",
                )
            )
            continue
        else:
            for field, value in values.items():
                setattr(episode, field, value)
            episode.import_batch = batch
            episode.updated_at = now
            to_update.append(episode)
            batch.updated_count += 1

        if row.parsed.fixes:
            batch.fixed_count += 1
            for fix in row.parsed.fixes:
                issues.append(
                    _issue(
                        batch,
                        row.line,
                        row.raw,
                        row.parsed.episode_id,
                        IssueSeverity.FIXED,
                        fix.code,
                        fix.message,
                    )
                )

    Episode.objects.bulk_create(to_create, batch_size=1000)
    Episode.objects.bulk_update(to_update, UPDATED_FIELDS, batch_size=1000)


def _check_header(fieldnames) -> None:
    if not fieldnames:
        raise ImportFailed("The file is empty.")
    present = {name.strip().lower() for name in fieldnames if name}
    missing = [column for column in COLUMNS if column not in present]
    if missing:
        raise ImportFailed(f"Missing required columns: {', '.join(missing)}.")


def _is_blank(raw: dict) -> bool:
    return all(
        not (value or "").strip() for key, value in raw.items() if key is not None and isinstance(value, str)
    )


def _issue(batch, line, raw, episode_id, severity, code, message) -> ImportRowIssue:
    # JSON keys must be strings: extra, unnamed columns arrive under the key None.
    raw_row = {("_extra" if key is None else key): value for key, value in raw.items()}
    return ImportRowIssue(
        batch=batch,
        row_number=line,
        episode_id=episode_id[:64],
        severity=severity,
        reason_code=code,
        message=message,
        raw_row=raw_row,
    )
