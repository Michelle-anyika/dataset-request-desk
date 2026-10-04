"""Idempotency keys: a retried POST (a timeout, a double click, a flaky network) does its work only once.

The client sends an ``Idempotency-Key`` header; repeating the same request with the same key replays the
first response instead of submitting, transitioning or importing again.
"""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import KNOWN_ROBOTS, ImportBatch, Robot
from apps.core.models import IdempotencyKey
from apps.requests_desk.models import DatasetRequest, RequestStatus
from tests.test_import_service import HEADER, ROW_1

REQUESTS = "/api/requests/"
pytestmark = pytest.mark.django_db


def payload(**overrides):
    deadline = (timezone.localdate() + timedelta(days=30)).isoformat()
    return {"task_name": "pick cup", "episodes_requested": 20, "deadline": deadline, **overrides}


def submit(client, key, **overrides):
    return client.post(REQUESTS, payload(**overrides), format="json", headers={"Idempotency-Key": key})


@pytest.fixture
def client(api_as):
    return api_as("client")


def test_a_retry_with_the_same_key_replays_the_first_response(client):
    first = submit(client, "submit-1")
    retry = submit(client, "submit-1")

    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert DatasetRequest.objects.count() == 1


def test_without_a_key_every_post_is_new(client):
    client.post(REQUESTS, payload(), format="json")
    client.post(REQUESTS, payload(), format="json")

    assert DatasetRequest.objects.count() == 2


def test_different_keys_are_different_requests(client):
    submit(client, "submit-1")
    submit(client, "submit-2")

    assert DatasetRequest.objects.count() == 2


def test_keys_belong_to_one_user(client, api_as):
    submit(client, "submit-1")
    response = submit(api_as("client"), "submit-1")

    assert response.status_code == 201
    assert "Idempotent-Replayed" not in response.headers
    assert DatasetRequest.objects.count() == 2


def test_reusing_a_key_for_a_different_request_is_refused(client):
    submit(client, "submit-1")

    response = submit(client, "submit-1", episodes_requested=99)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_reused"
    assert DatasetRequest.objects.count() == 1


def test_a_failed_request_is_not_remembered(client):
    # Nothing was created, so fixing the input and retrying with the same key must work.
    assert submit(client, "submit-1", episodes_requested=0).status_code == 400

    assert submit(client, "submit-1").status_code == 201


def test_a_key_still_in_use_is_refused(client):
    # Another request with this key is still running (e.g. the first attempt, before its response).
    IdempotencyKey.objects.create(user=client.user, key="submit-1", fingerprint="running")

    response = submit(client, "submit-1")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_in_use"
    assert DatasetRequest.objects.count() == 0


def test_keys_expire_after_a_day(client):
    submit(client, "submit-1")
    IdempotencyKey.objects.update(created_at=timezone.now() - timedelta(hours=25))

    response = submit(client, "submit-1")

    assert response.status_code == 201
    assert "Idempotent-Replayed" not in response.headers
    assert DatasetRequest.objects.count() == 2


def test_expired_keys_are_purged(client):
    submit(client, "old")
    submit(client, "recent")
    IdempotencyKey.objects.filter(key="old").update(created_at=timezone.now() - timedelta(hours=25))

    call_command("purge_idempotency_keys", verbosity=0)

    assert list(IdempotencyKey.objects.values_list("key", flat=True)) == ["recent"]


@pytest.mark.parametrize("key", ["", "x" * 256, "has\nnewline"])
def test_a_malformed_key_is_refused(client, key):
    response = submit(client, key)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_a_retried_transition_is_not_a_conflict(client, api_as):
    operator = api_as("operator")
    request = submit(client, "submit-1").json()
    url = f"{REQUESTS}{request['id']}/transitions/"

    def start():
        body = {"to_status": "in_progress"}
        return operator.post(url, body, format="json", headers={"Idempotency-Key": "start-1"})

    first, retry = start(), start()

    # Without the key the retry would be 409 (already in progress): the client couldn't tell it succeeded.
    assert first.status_code == retry.status_code == 200
    assert DatasetRequest.objects.get().status == RequestStatus.IN_PROGRESS


def test_a_retried_import_runs_once(api_as):
    for robot_id in KNOWN_ROBOTS:
        Robot.objects.create(id=robot_id, kind=Robot.kind_from_id(robot_id))
    operator = api_as("operator")
    content = f"{HEADER}\n{ROW_1}\n".encode()

    def upload():
        return operator.post(
            "/api/imports/",
            {"file": SimpleUploadedFile("export.csv", content, "text/csv")},
            format="multipart",
            headers={"Idempotency-Key": "import-1"},
        )

    first, retry = upload(), upload()

    assert first.status_code == retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert ImportBatch.objects.count() == 1


def test_idempotent_operations_document_the_header(api_as):
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    create = schema["paths"]["/api/requests/"]["post"]
    listing = schema["paths"]["/api/requests/"]["get"]

    assert {"in": "header", "name": "Idempotency-Key"}.items() <= next(
        p for p in create["parameters"] if p["name"] == "Idempotency-Key"
    ).items()
    assert {"409", "422"} <= set(create["responses"])
    assert all(p["name"] != "Idempotency-Key" for p in listing.get("parameters", []))
