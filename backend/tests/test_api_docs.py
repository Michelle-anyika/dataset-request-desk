import pytest

pytestmark = pytest.mark.django_db


def test_openapi_schema_and_docs_are_served_when_enabled(client, settings):
    settings.API_DOCS_ENABLED = True

    schema = client.get("/api/schema/")

    assert schema.status_code == 200
    assert b"/api/auth/login/" in schema.content
    assert client.get("/api/docs/").status_code == 200


def test_docs_are_hidden_when_disabled(client, settings):
    # Off by default in production: no need to publish a map of the API.
    settings.API_DOCS_ENABLED = False

    assert client.get("/api/schema/").status_code == 404
    assert client.get("/api/docs/").status_code == 404
