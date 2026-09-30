import pytest
from django.db import OperationalError, connection


@pytest.mark.django_db
def test_healthy_when_database_responds(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


@pytest.mark.django_db
def test_unhealthy_when_database_is_unreachable(client, monkeypatch):
    def unreachable():
        raise OperationalError("connection refused")

    monkeypatch.setattr(connection, "cursor", unreachable)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unavailable"}


def test_only_get_is_allowed(client):
    assert client.post("/health").status_code == 405


@pytest.mark.django_db
def test_is_never_cached(client):
    response = client.get("/health")

    assert "no-cache" in response["Cache-Control"]
