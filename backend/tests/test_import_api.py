from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.catalog.models import KNOWN_ROBOTS, Episode, ImportBatch, Robot
from tests.test_import_service import HEADER, ROW_1, ROW_2, SEED_FILE

IMPORTS = "/api/imports/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def robots():
    for robot_id in KNOWN_ROBOTS:
        Robot.objects.create(id=robot_id, kind=Robot.kind_from_id(robot_id))


def upload(client, content: bytes, name="export.csv"):
    return client.post(IMPORTS, {"file": SimpleUploadedFile(name, content, "text/csv")}, format="multipart")


def csv_bytes(*lines):
    return ("\n".join([HEADER, *lines]) + "\n").encode()


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_staff_upload_an_export_and_get_the_report(api_as, role):
    response = upload(api_as(role), csv_bytes(ROW_1, ROW_2, "EP-3,arm-99,x,2026-08-01T10:00:00,5,A,good"))

    assert response.status_code == 201
    report = response.json()
    assert report["status"] == "completed"
    assert (report["created_count"], report["skipped_count"]) == (2, 1)
    assert report["previously_imported"] is False
    assert Episode.objects.count() == 2


def test_the_same_file_uploaded_again_is_flagged_and_creates_nothing(api_as):
    operator = api_as("operator")
    upload(operator, csv_bytes(ROW_1))

    report = upload(operator, csv_bytes(ROW_1)).json()

    assert report["previously_imported"] is True
    assert (report["created_count"], report["unchanged_count"]) == (0, 1)


def test_clients_cannot_import(api_as):
    response = upload(api_as("client"), csv_bytes(ROW_1))

    assert response.status_code == 403
    assert Episode.objects.count() == 0


def test_a_file_is_required(api_as):
    response = api_as("operator").post(IMPORTS, {}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_only_csv_files_are_accepted(api_as):
    response = upload(api_as("operator"), b"MZ\x90\x00", name="payload.exe")

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_oversized_files_are_refused(api_as, settings):
    settings.IMPORT_MAX_UPLOAD_BYTES = 100

    response = upload(api_as("operator"), csv_bytes(ROW_1, ROW_2, ROW_1))

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]


def test_a_file_that_is_not_utf8_text_fails_cleanly(api_as):
    response = upload(api_as("operator"), HEADER.encode() + b"\n\xff\xfe\xfa broken")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_file"
    assert ImportBatch.objects.get().status == "failed"


def test_a_missing_column_fails_with_the_reason(api_as):
    response = upload(api_as("operator"), b"episode_id,robot_id\nEP-1,arm-01\n")

    assert response.status_code == 400
    assert "quality" in response.json()["error"]["message"]


def test_import_history_and_issues_are_browsable(api_as):
    operator = api_as("operator")
    batch_id = upload(operator, csv_bytes(ROW_1, "EP-3,arm-99,x,2026-08-01T10:00:00,5,A,Good")).json()["id"]

    listing = operator.get(IMPORTS).json()
    detail = operator.get(f"{IMPORTS}{batch_id}/").json()
    skipped = operator.get(f"{IMPORTS}{batch_id}/issues/", {"severity": "skipped"}).json()

    assert [b["id"] for b in listing["results"]] == [batch_id]
    assert detail["uploaded_by"]["full_name"] == operator.user.full_name
    assert [(i["row_number"], i["reason_code"]) for i in skipped["results"]] == [(3, "unknown_robot")]
    assert skipped["results"][0]["raw_row"]["robot_id"] == "arm-99"


def test_clients_cannot_see_imports(api_as):
    assert api_as("client").get(IMPORTS).status_code == 403


def test_listing_imports_uses_a_fixed_number_of_queries(api_as, django_assert_max_num_queries):
    operator = api_as("operator")
    for _ in range(5):
        upload(operator, csv_bytes(ROW_1))

    with django_assert_max_num_queries(2):
        operator.get(IMPORTS)


class TestCommand:
    def test_imports_a_file_and_prints_the_summary(self, make_user):
        make_user(email="ops@example.com", role="operator")
        out = StringIO()

        call_command("import_episodes", str(SEED_FILE), "--as", "ops@example.com", stdout=out)

        output = out.getvalue()
        assert "created" in output
        assert "skipped" in output
        assert "unknown_robot" in output
        assert Episode.objects.exists()

    def test_once_skips_a_file_that_was_already_imported(self, make_user):
        make_user(email="ops@example.com", role="operator")
        call_command(
            "import_episodes", str(SEED_FILE), "--as", "ops@example.com", "--once", stdout=StringIO()
        )
        out = StringIO()

        call_command("import_episodes", str(SEED_FILE), "--as", "ops@example.com", "--once", stdout=out)

        assert "already imported" in out.getvalue()
        assert ImportBatch.objects.count() == 1

    def test_requires_a_staff_account(self, make_user):
        make_user(email="client@example.com", role="client")

        with pytest.raises(Exception, match="operator or admin"):
            call_command("import_episodes", str(SEED_FILE), "--as", "client@example.com", stdout=StringIO())
