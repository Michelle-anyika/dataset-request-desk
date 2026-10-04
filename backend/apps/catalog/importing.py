"""Turning one row of the recording system's CSV export into a clean episode (PLAN.md §8).

``parse_row`` is pure: it either returns the cleaned values plus the list of fixes it applied, or raises
``RowRejected`` with a reason code. Everything that needs the database (duplicates, upserts) lives in the
import service.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.catalog.models import Quality
from apps.catalog.normalise import normalise_task_name

COLUMNS = (
    "episode_id",
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
)
MAX_DURATION_SECONDS = 3600  # an hour; the export's longest real clip is two minutes
CLOCK_SKEW = timedelta(minutes=5)  # recording machines' clocks may run slightly ahead

_EPISODE_ID = re.compile(r"EP-\d+")
# The export's canonical format first; the others are accepted and reported as reformatted.
_CANONICAL_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
_OTHER_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")  # day first, as in Rwanda and Europe


@dataclass(frozen=True)
class Fix:
    code: str
    message: str


@dataclass(frozen=True)
class ParsedRow:
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int
    operator_name: str
    quality: str
    fixes: tuple[Fix, ...] = ()

    def values(self) -> dict:
        """The stored fields, for creating or comparing an episode."""
        return {
            "robot_id": self.robot_id,
            "task_name": self.task_name,
            "recorded_at": self.recorded_at,
            "duration_seconds": self.duration_seconds,
            "operator_name": self.operator_name,
            "quality": self.quality,
        }


class RowRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_row(raw: dict, *, known_robots: set[str], now: datetime) -> ParsedRow:
    if None in raw or any(raw.get(column) is None for column in COLUMNS):
        raise RowRejected("malformed_row", f"Expected {len(COLUMNS)} columns.")

    fixes: list[Fix] = []
    episode_id = _episode_id(raw["episode_id"], fixes)
    robot_id = _robot_id(raw["robot_id"], known_robots, fixes)
    task_name = _task_name(raw["task_name"], fixes)
    recorded_at = _recorded_at(raw["recorded_at"], now, fixes)
    duration_seconds = _duration(raw["duration_seconds"], fixes)
    operator_name = _operator_name(raw["operator_name"], fixes)
    quality = _quality(raw["quality"], fixes)
    return ParsedRow(
        episode_id, robot_id, task_name, recorded_at, duration_seconds, operator_name, quality, tuple(fixes)
    )


def _episode_id(raw: str, fixes: list[Fix]) -> str:
    value = raw.strip()
    if not value:
        raise RowRejected("missing_episode_id", "The episode id is empty.")
    normalised = value.upper()
    if not _EPISODE_ID.fullmatch(normalised):
        raise RowRejected("invalid_episode_id", f"{value!r} is not an episode id like EP-00123.")
    if normalised != raw:
        fixes.append(Fix("episode_id_normalised", f"{raw!r} stored as {normalised!r}."))
    return normalised


def _robot_id(raw: str, known_robots: set[str], fixes: list[Fix]) -> str:
    value = raw.strip()
    if not value:
        raise RowRejected("missing_robot_id", "The robot id is empty.")
    if value not in known_robots:
        raise RowRejected("unknown_robot", f"Robot {value!r} is not a known robot.")
    if value != raw:
        fixes.append(Fix("robot_id_trimmed", f"{raw!r} stored as {value!r}."))
    return value


def _task_name(raw: str, fixes: list[Fix]) -> str:
    value = normalise_task_name(raw)
    if not value:
        raise RowRejected("missing_task_name", "The task name is empty.")
    if len(value) > 120:
        raise RowRejected("task_name_too_long", "The task name is longer than 120 characters.")
    if value != raw:
        fixes.append(Fix("task_name_normalised", f"{raw!r} stored as {value!r}."))
    return value


def _recorded_at(raw: str, now: datetime, fixes: list[Fix]) -> datetime:
    value = raw.strip()
    if not value:
        raise RowRejected("missing_recorded_at", "The recording time is empty.")

    parsed = _parse_iso(value)
    if parsed is None:
        parsed = _parse_other_formats(value)
        if parsed is None:
            raise RowRejected("invalid_recorded_at", f"{value!r} is not a recognised date and time.")
        fixes.append(Fix("recorded_at_reformatted", f"{value!r} read as {parsed.isoformat()}."))

    if parsed > now + CLOCK_SKEW:
        raise RowRejected("recorded_at_in_future", f"{parsed.isoformat()} is in the future.")
    return parsed


def _parse_iso(value: str) -> datetime | None:
    # The canonical format, optionally with an explicit UTC designator. Naive times are UTC (PLAN §8).
    for candidate in (value, value.removesuffix("Z")):
        try:
            parsed = datetime.strptime(candidate, _CANONICAL_DATE_FORMAT)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    return None


def _parse_other_formats(value: str) -> datetime | None:
    for date_format in _OTHER_DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _duration(raw: str, fixes: list[Fix]) -> int:
    value = raw.strip()
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise RowRejected("invalid_duration", f"{value!r} is not a number of seconds.") from None
    if not number.is_finite():
        raise RowRejected("invalid_duration", f"{value!r} is not a number of seconds.")

    seconds = int(number.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if seconds <= 0:
        raise RowRejected("invalid_duration", f"{value!r} is not a positive duration.")
    if seconds > MAX_DURATION_SECONDS:
        raise RowRejected("duration_out_of_range", f"{value} seconds is longer than {MAX_DURATION_SECONDS}.")
    if Decimal(seconds) != number:
        fixes.append(Fix("duration_rounded", f"{value} rounded to {seconds} seconds."))
    return seconds


def _operator_name(raw: str, fixes: list[Fix]) -> str:
    value = raw.strip()
    if not value:
        fixes.append(Fix("operator_name_missing", "Imported without an operator name."))
    return value


def _quality(raw: str, fixes: list[Fix]) -> str:
    value = raw.strip().lower()
    if not value:
        raise RowRejected("missing_quality", "The quality is empty.")
    if value not in Quality.values:
        raise RowRejected("invalid_quality", f"{raw.strip()!r} is not good, usable or bad.")
    if value != raw:
        fixes.append(Fix("quality_normalised", f"{raw!r} stored as {value!r}."))
    return value
