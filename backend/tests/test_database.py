import pytest
from django.db import connection


@pytest.mark.django_db
def test_runs_against_postgresql():
    # Partial unique indexes and percentile_cont are Postgres features the domain rules rely on,
    # so the suite must never silently fall back to another database.
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
