import io
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.catalog.import_service import ImportFailed, import_episodes
from apps.catalog.models import KNOWN_ROBOTS, Episode, ImportBatch, ImportStatus, Quality, Robot
from apps.requests_desk.models import Assignment
from apps.requests_desk.services import submit_request

HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality"
SEED_FILE = Path(settings.BASE_DIR) / "seed" / "episodes.csv"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def robots():
    for robot_id in KNOWN_ROBOTS:
        Robot.objects.create(id=robot_id, kind=Robot.kind_from_id(robot_id))


@pytest.fixture
def operator(make_user):
    return make_user(email="ops@example.com", role="operator")


def csv_file(*lines, header=HEADER):
    return io.StringIO("\n".join([header, *lines]) + "\n")


def run(operator, *lines, header=HEADER):
    return import_episodes(csv_file(*lines, header=header), file_name="export.csv", uploaded_by=operator)


def issues(batch, severity=None):
    queryset = batch.issues.all()
    if severity:
        queryset = queryset.filter(severity=severity)
    return [(i.row_number, i.reason_code) for i in queryset]


ROW_1 = "EP-00001,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good"
ROW_2 = "EP-00002,arm-02,fold towel,2026-08-02T10:00:00,40,Eric,usable"


class TestCreatingAndReporting:
    def test_creates_episodes_and_reports_counts(self, operator):
        batch = run(operator, ROW_1, ROW_2)

        assert batch.status == ImportStatus.COMPLETED
        assert (batch.total_rows, batch.created_count, batch.skipped_count) == (2, 2, 0)
        assert batch.finished_at is not None
        episode = Episode.objects.get(episode_id="EP-00001")
        assert (episode.robot_id, episode.task_name, episode.quality) == ("arm-01", "pick cup", "good")
        assert episode.import_batch == batch

    def test_records_the_uploader_file_name_and_hash(self, operator):
        batch = run(operator, ROW_1)

        assert batch.uploaded_by == operator
        assert batch.file_name == "export.csv"
        assert len(batch.file_sha256) == 64

    def test_skipped_rows_are_reported_with_line_and_reason(self, operator):
        batch = run(operator, ROW_1, "EP-00002,arm-99,fold towel,2026-08-02T10:00:00,40,Eric,good")

        assert (batch.created_count, batch.skipped_count) == (1, 1)
        [issue] = batch.issues.all()
        assert (issue.row_number, issue.severity, issue.reason_code) == (3, "skipped", "unknown_robot")
        assert issue.episode_id == "EP-00002"
        assert issue.raw_row["robot_id"] == "arm-99"

    def test_fixed_rows_are_imported_and_reported(self, operator):
        batch = run(operator, "ep-00007,arm-01,  Pick Cup ,2026-08-01T10:00:00,30,Aline,Good")

        assert batch.created_count == 1
        assert batch.fixed_count == 1
        assert issues(batch, "fixed") == [
            (2, "episode_id_normalised"),
            (2, "task_name_normalised"),
            (2, "quality_normalised"),
        ]

    def test_a_line_of_only_spaces_is_skipped_as_blank(self, operator):
        batch = run(operator, ROW_1, "   ")

        assert issues(batch) == [(3, "blank_line")]


class TestIdempotency:
    def test_importing_the_same_file_twice_creates_no_duplicates(self, operator):
        run(operator, ROW_1, ROW_2)

        second = run(operator, ROW_1, ROW_2)

        assert Episode.objects.count() == 2
        assert (second.created_count, second.updated_count, second.unchanged_count) == (0, 0, 2)

    def test_a_changed_row_updates_the_episode(self, operator):
        run(operator, ROW_1)

        second = run(operator, ROW_1.replace(",good", ",usable"))

        assert (second.created_count, second.updated_count) == (0, 1)
        episode = Episode.objects.get(episode_id="EP-00001")
        assert episode.quality == "usable"
        assert episode.import_batch == second

    def test_an_assigned_episode_cannot_be_downgraded_to_bad(self, operator):
        run(operator, ROW_1)
        client = operator.__class__.objects.create_user(email="c@example.com", password="x", full_name="C")
        request = submit_request(
            client,
            task_name="pick cup",
            episodes_requested=1,
            deadline=timezone.localdate() + timedelta(days=7),
        )
        Assignment.objects.create(
            request=request, episode=Episode.objects.get(episode_id="EP-00001"), assigned_by=operator
        )

        batch = run(operator, ROW_1.replace(",good", ",bad"))

        assert issues(batch) == [(2, "assigned_episode_conflict")]
        assert Episode.objects.get(episode_id="EP-00001").quality == Quality.GOOD


class TestDuplicatesWithinAFile:
    def test_an_exact_duplicate_is_skipped(self, operator):
        batch = run(operator, ROW_1, ROW_1)

        assert batch.created_count == 1
        assert issues(batch) == [(3, "duplicate_in_file")]

    def test_a_conflicting_duplicate_keeps_the_first_row(self, operator):
        batch = run(operator, ROW_1, ROW_1.replace(",good", ",bad"))

        assert issues(batch) == [(3, "conflicting_duplicate")]
        assert Episode.objects.get(episode_id="EP-00001").quality == "good"
        assert "line 2" in batch.issues.get().message

    def test_ids_differing_only_in_case_are_the_same_episode(self, operator):
        batch = run(operator, ROW_1, ROW_1.replace("EP-00001", "ep-00001").replace("arm-01", "arm-02"))

        assert "conflicting_duplicate" in [code for _, code in issues(batch, "skipped")]


class TestInvalidFiles:
    def test_a_missing_column_fails_the_whole_import(self, operator):
        with pytest.raises(ImportFailed, match="quality"):
            run(operator, ROW_1, header=HEADER.replace(",quality", ""))

        batch = ImportBatch.objects.get()
        assert batch.status == ImportStatus.FAILED
        assert "quality" in batch.error_message
        assert Episode.objects.count() == 0

    def test_an_empty_file_fails(self, operator):
        with pytest.raises(ImportFailed):
            import_episodes(io.StringIO(""), file_name="empty.csv", uploaded_by=operator)


def import_seed_file(operator):
    with SEED_FILE.open(newline="") as export:  # newline="": the csv module handles CRLF itself
        return import_episodes(export, file_name="episodes.csv", uploaded_by=operator)


class TestTheRealExport:
    """seed/episodes.csv: every messy case from PLAN.md §8 in one file."""

    def outcome(self, batch, episode_id):
        return {i.reason_code for i in batch.issues.filter(episode_id=episode_id)}

    def test_every_row_is_accounted_for(self, operator):
        batch = import_seed_file(operator)

        accounted = batch.created_count + batch.updated_count + batch.unchanged_count + batch.skipped_count
        assert batch.status == ImportStatus.COMPLETED
        assert accounted == batch.total_rows
        assert Episode.objects.count() == batch.created_count

    def test_known_problem_rows_get_the_decided_outcome(self, operator):
        batch = import_seed_file(operator)

        assert "conflicting_duplicate" in self.outcome(batch, "EP-00011")  # bad vs good
        assert "conflicting_duplicate" in self.outcome(batch, "EP-00003")  # from the ep-00003 row
        assert "duplicate_in_file" in self.outcome(batch, "EP-00030")
        assert "unknown_robot" in self.outcome(batch, "EP-00024")
        assert "recorded_at_in_future" in self.outcome(batch, "EP-00025")
        assert "duration_out_of_range" in self.outcome(batch, "EP-90004")
        assert "invalid_quality" in self.outcome(batch, "EP-00020")
        assert "malformed_row" in self.outcome(batch, "EP-90001")
        assert Episode.objects.get(episode_id="EP-90002").task_name == "pick cup, then place"
        assert Episode.objects.get(episode_id="EP-00018").duration_seconds == 46  # 45.5 rounded
        assert Episode.objects.get(episode_id="EP-90005").operator_name == ""

    def test_reimporting_the_export_changes_nothing(self, operator):
        first = import_seed_file(operator)

        second = import_seed_file(operator)

        assert second.created_count == 0
        assert second.updated_count == 0
        assert second.unchanged_count == first.created_count
        assert second.skipped_count == first.skipped_count
        assert Episode.objects.count() == first.created_count
