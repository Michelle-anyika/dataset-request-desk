"""Row-level rules for the episode import: one test per messy case decided in PLAN.md §8."""

from datetime import UTC, datetime

import pytest

from apps.catalog.importing import RowRejected, parse_row

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}

VALID = {
    "episode_id": "EP-00156",
    "robot_id": "mobile-01",
    "task_name": "stack blocks",
    "recorded_at": "2026-08-16T23:28:00",
    "duration_seconds": "78",
    "operator_name": "Diane",
    "quality": "good",
}


def parse(**overrides):
    return parse_row({**VALID, **overrides}, known_robots=KNOWN_ROBOTS, now=NOW)


def rejection(**overrides):
    with pytest.raises(RowRejected) as caught:
        parse(**overrides)
    return caught.value.code


def fix_codes(row):
    return [fix.code for fix in row.fixes]


def test_a_clean_row_is_parsed_without_fixes():
    row = parse()

    assert row.episode_id == "EP-00156"
    assert row.robot_id == "mobile-01"
    assert row.task_name == "stack blocks"
    assert row.recorded_at == datetime(2026, 8, 16, 23, 28, tzinfo=UTC)  # naive timestamps are UTC
    assert row.duration_seconds == 78
    assert row.operator_name == "Diane"
    assert row.quality == "good"
    assert row.fixes == ()


class TestFixedAndImported:
    def test_lower_case_episode_id(self):
        row = parse(episode_id="ep-00003")

        assert row.episode_id == "EP-00003"
        assert fix_codes(row) == ["episode_id_normalised"]

    def test_robot_id_with_whitespace(self):
        row = parse(robot_id=" arm-01")

        assert row.robot_id == "arm-01"
        assert fix_codes(row) == ["robot_id_trimmed"]

    @pytest.mark.parametrize("raw", ["  Pick Cup ", "PICK CUP", "pick   cup"])
    def test_task_name_casing_and_whitespace(self, raw):
        row = parse(task_name=raw)

        assert row.task_name == "pick cup"
        assert fix_codes(row) == ["task_name_normalised"]

    def test_task_name_with_a_comma_is_kept(self):
        # Quoted in the file ("pick cup, then place"); the csv module has already unquoted it.
        assert parse(task_name="pick cup, then place").task_name == "pick cup, then place"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-08-14 09:12:00", datetime(2026, 8, 14, 9, 12, tzinfo=UTC)),
            ("14/08/2026 09:15", datetime(2026, 8, 14, 9, 15, tzinfo=UTC)),  # day first
        ],
    )
    def test_alternative_date_formats(self, raw, expected):
        row = parse(recorded_at=raw)

        assert row.recorded_at == expected
        assert fix_codes(row) == ["recorded_at_reformatted"]

    def test_explicit_utc_designator_needs_no_fix(self):
        row = parse(recorded_at="2026-08-14T09:20:00Z")

        assert row.recorded_at == datetime(2026, 8, 14, 9, 20, tzinfo=UTC)
        assert row.fixes == ()

    def test_decimal_duration_is_rounded_to_the_nearest_second(self):
        row = parse(duration_seconds="45.5")

        assert row.duration_seconds == 46
        assert fix_codes(row) == ["duration_rounded"]

    @pytest.mark.parametrize("raw", ["Good", "USABLE", " bad "])
    def test_quality_casing(self, raw):
        row = parse(quality=raw)

        assert row.quality == raw.strip().lower()
        assert fix_codes(row) == ["quality_normalised"]

    def test_missing_operator_name_is_allowed(self):
        row = parse(operator_name="")

        assert row.operator_name == ""
        assert fix_codes(row) == ["operator_name_missing"]

    def test_several_fixes_are_all_reported(self):
        row = parse(episode_id="ep-00006", task_name="  Pick Cup ", quality="Good")

        assert fix_codes(row) == ["episode_id_normalised", "task_name_normalised", "quality_normalised"]


class TestSkipped:
    @pytest.mark.parametrize("raw", ["", "   "])
    def test_missing_episode_id(self, raw):
        assert rejection(episode_id=raw) == "missing_episode_id"

    @pytest.mark.parametrize("raw", ["EP 001", "00156", "EP-", "EP-12A"])
    def test_malformed_episode_id(self, raw):
        assert rejection(episode_id=raw) == "invalid_episode_id"

    def test_missing_robot(self):
        assert rejection(robot_id="") == "missing_robot_id"

    def test_unknown_robot(self):
        assert rejection(robot_id="arm-99") == "unknown_robot"

    def test_missing_task_name(self):
        assert rejection(task_name="  ") == "missing_task_name"

    def test_task_name_too_long(self):
        assert rejection(task_name="x" * 121) == "task_name_too_long"

    @pytest.mark.parametrize("raw", ["not a date", "2026-13-01T00:00:00", "32/01/2026 10:00"])
    def test_unparseable_date(self, raw):
        assert rejection(recorded_at=raw) == "invalid_recorded_at"

    def test_missing_date(self):
        assert rejection(recorded_at="") == "missing_recorded_at"

    def test_date_in_the_future(self):
        assert rejection(recorded_at="2031-01-01T00:00:00") == "recorded_at_in_future"

    @pytest.mark.parametrize("raw", ["", "N/A", "abc"])
    def test_missing_or_non_numeric_duration(self, raw):
        assert rejection(duration_seconds=raw) == "invalid_duration"

    @pytest.mark.parametrize("raw", ["0", "-5"])
    def test_duration_must_be_positive(self, raw):
        assert rejection(duration_seconds=raw) == "invalid_duration"

    def test_implausibly_long_duration(self):
        assert rejection(duration_seconds="999999") == "duration_out_of_range"

    def test_unknown_quality(self):
        assert rejection(quality="excellent") == "invalid_quality"

    def test_missing_quality(self):
        assert rejection(quality="") == "missing_quality"

    def test_row_with_missing_columns(self):
        # csv.DictReader fills absent trailing columns with None.
        assert rejection(operator_name=None, quality=None) == "malformed_row"

    def test_row_with_extra_columns(self):
        with pytest.raises(RowRejected) as caught:
            parse_row({**VALID, None: ["unexpected"]}, known_robots=KNOWN_ROBOTS, now=NOW)

        assert caught.value.code == "malformed_row"

    def test_rejection_message_names_the_value(self):
        with pytest.raises(RowRejected) as caught:
            parse(robot_id="arm-99")

        assert "arm-99" in caught.value.message
