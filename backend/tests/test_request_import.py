"""Migrating the spreadsheet's requests (issue #37): preview, then commit, safely re-runnable."""

from io import BytesIO, StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from openpyxl import Workbook

from apps.notifications.models import Notification
from apps.requests_desk.models import DatasetRequest, RequestStatusEvent

PREVIEW = "/api/request-imports/preview/"
COMMIT = "/api/request-imports/"
HEADER = "reference,client_email,task_name,episodes_requested,deadline,notes,status"

pytestmark = pytest.mark.django_db


@pytest.fixture
def clients(make_user):
    return {
        "acme": make_user(email="buyer@acme.example", role="client"),
        "beta": make_user(email="lab@beta.example", role="client"),
    }


def sheet(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def send(client, url, content: bytes, name="requests.csv"):
    return client.post(url, {"file": SimpleUploadedFile(name, content, "text/csv")}, format="multipart")


GOOD = [
    "SR-001,buyer@acme.example,Pick Cup,200,2026-11-01,Kitchen only,submitted",
    "SR-002,LAB@beta.example,fold towel,50,2026-09-01,,In progress",
    "SR-003,buyer@acme.example,open drawer,20,2026-06-01,Old one,accepted",
]


def test_the_preview_says_what_would_happen_and_saves_nothing(api_as, clients):
    response = send(api_as("admin"), PREVIEW, sheet(*GOOD))

    assert response.status_code == 200
    report = response.json()
    assert (report["create"], report["unchanged"], report["skip"]) == (3, 0, 0)
    first = report["rows"][0]
    assert first == {
        "row": 2,
        "reference": "SR-001",
        "action": "create",
        "reason_code": "",
        "message": "",
        "client_email": "buyer@acme.example",
        "task_name": "pick cup",
        "status": "submitted",
    }
    assert DatasetRequest.objects.count() == 0


def test_committing_creates_the_requests_with_their_status_and_an_imported_event(api_as, clients):
    admin = api_as("admin")

    response = send(admin, COMMIT, sheet(*GOOD))

    assert response.status_code == 201
    assert response.json()["create"] == 3
    by_ref = {request.spreadsheet_ref: request for request in DatasetRequest.objects.all()}
    assert by_ref["SR-002"].client == clients["beta"]  # email matched case-insensitively
    assert by_ref["SR-002"].status == "in_progress"
    assert by_ref["SR-003"].status == "accepted"
    event = RequestStatusEvent.objects.get(request=by_ref["SR-001"])
    assert (event.from_status, event.to_status, event.changed_by) == (None, "submitted", admin.user)
    assert "Imported from the spreadsheet" in event.comment
    assert "SR-001" in event.comment


def test_a_migration_sends_no_notifications(api_as, clients):
    send(api_as("admin"), COMMIT, sheet(*GOOD))

    assert Notification.objects.count() == 0


def test_running_it_again_creates_nothing(api_as, clients):
    admin = api_as("admin")
    send(admin, COMMIT, sheet(*GOOD))

    again = send(admin, COMMIT, sheet(*GOOD)).json()

    assert (again["create"], again["unchanged"]) == (0, 3)
    assert {row["action"] for row in again["rows"]} == {"unchanged"}
    assert DatasetRequest.objects.count() == 3


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ("SR-9,nobody@example.com,pick cup,10,2026-11-01,,submitted", "unknown_client"),
        ("SR-9,{operator},pick cup,10,2026-11-01,,submitted", "not_a_client"),
        ("SR-9,buyer@acme.example,pick cup,10,2026-11-01,,finished", "invalid_status"),
        ("SR-9,buyer@acme.example,pick cup,10,2026-11-01,,delivered", "delivered_needs_episodes"),
        ("SR-9,buyer@acme.example,pick cup,0,2026-11-01,,submitted", "invalid_episodes_requested"),
        ("SR-9,buyer@acme.example,pick cup,ten,2026-11-01,,submitted", "invalid_episodes_requested"),
        ("SR-9,buyer@acme.example,pick cup,10,next week,,submitted", "invalid_deadline"),
        ("SR-9,buyer@acme.example,  ,10,2026-11-01,,submitted", "missing_task_name"),
        (",buyer@acme.example,pick cup,10,2026-11-01,,submitted", "missing_reference"),
        ("SR-9,buyer@acme.example,pick cup,10,2026-11-01", "malformed_row"),
        (f"SR-{'9' * 70},buyer@acme.example,pick cup,10,2026-11-01,,submitted", "invalid_reference"),
        (f"SR-9,buyer@acme.example,{'x' * 121},10,2026-11-01,,submitted", "invalid_task_name"),
        (f"SR-9,buyer@acme.example,pick cup,10,2026-11-01,{'n' * 2001},submitted", "invalid_notes"),
    ],
)
def test_each_problem_is_reported_not_guessed(api_as, clients, make_user, row, code):
    make_user(email="ops@example.com", role="operator")

    report = send(api_as("admin"), COMMIT, sheet(GOOD[0], row.format(operator="ops@example.com"))).json()

    assert (report["create"], report["skip"]) == (1, 1)
    assert report["rows"][1]["reason_code"] == code
    assert report["rows"][1]["message"]
    assert DatasetRequest.objects.count() == 1  # the good row is imported, the bad one only reported


def test_a_reference_repeated_in_the_file_is_imported_once(api_as, clients):
    report = send(api_as("admin"), COMMIT, sheet(GOOD[0], GOOD[0])).json()

    assert [row["reason_code"] for row in report["rows"]] == ["", "duplicate_reference"]
    assert DatasetRequest.objects.count() == 1


def test_past_deadlines_are_kept_as_they_were(api_as, clients):
    send(api_as("admin"), COMMIT, sheet("SR-1,buyer@acme.example,pick cup,10,2020-01-01,,in_progress"))

    assert str(DatasetRequest.objects.get().deadline) == "2020-01-01"


def test_an_excel_workbook_works_too(api_as, clients):
    book = Workbook()
    for row in [HEADER, GOOD[0]]:
        book.active.append(row.split(","))
    content = BytesIO()
    book.save(content)

    report = send(api_as("admin"), PREVIEW, content.getvalue(), name="requests.xlsx").json()

    assert report["create"] == 1


def test_a_missing_column_fails_with_the_reason(api_as, clients):
    response = send(api_as("admin"), PREVIEW, b"reference,client_email\nSR-1,buyer@acme.example\n")

    assert response.status_code == 400
    assert "Missing required columns" in response.json()["error"]["message"]


@pytest.mark.parametrize("role", ["client", "operator"])
def test_only_admins_can_migrate(api_as, clients, role):
    for url in (PREVIEW, COMMIT):
        assert send(api_as(role), url, sheet(*GOOD)).status_code == 403
    assert DatasetRequest.objects.count() == 0


def test_the_command_previews_by_default_and_commits_when_asked(make_user, clients, tmp_path):
    make_user(email="admin@example.com", role="admin")
    path = tmp_path / "requests.csv"
    path.write_bytes(sheet(*GOOD))
    out = StringIO()

    call_command("import_requests", str(path), "--as", "admin@example.com", stdout=out)
    assert DatasetRequest.objects.count() == 0
    assert "Preview" in out.getvalue()

    call_command("import_requests", str(path), "--as", "admin@example.com", "--commit", stdout=out)
    assert DatasetRequest.objects.count() == 3


def test_the_command_requires_an_admin(make_user, clients, tmp_path):
    make_user(email="ops@example.com", role="operator")
    path = tmp_path / "requests.csv"
    path.write_bytes(sheet(*GOOD))

    with pytest.raises(Exception, match="admin"):
        call_command("import_requests", str(path), "--as", "ops@example.com", stdout=StringIO())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\n", "The file is empty."),
        (b"reference,\xff\xfe\n", "not UTF-8"),
        (HEADER.encode() + b"\n" + b"x" * 200_000 + b"\n", "not valid CSV"),  # over the csv field limit
    ],
)
def test_a_file_that_cannot_be_read_fails_with_the_reason(api_as, content, message):
    response = send(api_as("admin"), PREVIEW, content)

    assert response.status_code == 400
    assert message in response.json()["error"]["message"]


def test_the_command_lists_skipped_rows_and_reports_unreadable_files(make_user, clients, tmp_path):
    make_user(email="admin@example.com", role="admin")
    path = tmp_path / "requests.csv"
    path.write_bytes(sheet(GOOD[0], "SR-9,nobody@example.com,pick cup,10,2026-11-01,,submitted"))
    out = StringIO()

    call_command("import_requests", str(path), "--as", "admin@example.com", stdout=out)

    assert "row 3 (SR-9): unknown_client" in out.getvalue()
    missing = str(tmp_path / "missing.csv")
    with pytest.raises(Exception, match="No such file"):
        call_command("import_requests", missing, "--as", "admin@example.com", stdout=out)


def test_a_csv_error_shows_our_message_not_the_csv_modules(api_as):
    content = HEADER.encode() + b"\n" + b"x" * 200_000 + b"\n"

    message = send(api_as("admin"), PREVIEW, content).json()["error"]["message"]

    assert message == "The file is not valid CSV. Export it again as CSV (comma-separated, UTF-8)."
    assert "field limit" not in message
