"""Analytics queries. Every number is aggregated by PostgreSQL; no rows are loaded into Python to be counted.

A date range is inclusive and measured in UTC days: ``[from 00:00, to + 1 day 00:00)``.
"""

from datetime import UTC, date, datetime, time, timedelta

from django.db import connection
from django.db.models import Count
from django.db.models.functions import TruncDate

from apps.catalog.models import Episode, Quality
from apps.requests_desk.models import DatasetRequest, RequestStatus

TOP_TASKS = 5


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def episodes_per_day(start: date, end: date) -> list[dict]:
    """Episodes recorded per UTC day per robot. Served by the (recorded_at, robot) index."""
    low, high = _bounds(start, end)
    rows = (
        Episode.objects.filter(recorded_at__gte=low, recorded_at__lt=high)
        .annotate(day=TruncDate("recorded_at", tzinfo=UTC))
        .values("day", "robot_id")
        .annotate(episodes=Count("id"))
        .order_by("day", "robot_id")
    )
    return [
        {"date": r["day"].isoformat(), "robot_id": r["robot_id"], "episodes": r["episodes"]} for r in rows
    ]


def top_tasks_by_good_episodes(start: date, end: date) -> list[dict]:
    low, high = _bounds(start, end)
    rows = (
        Episode.objects.filter(quality=Quality.GOOD, recorded_at__gte=low, recorded_at__lt=high)
        .values("task_name")
        .annotate(good_episodes=Count("id"))
        .order_by("-good_episodes", "task_name")[:TOP_TASKS]
    )
    return list(rows)


def requests_by_status(start: date, end: date) -> dict[str, int]:
    """Current status of the requests submitted in the range. Every status is present, zero or not."""
    low, high = _bounds(start, end)
    counts = dict(
        DatasetRequest.objects.filter(created_at__gte=low, created_at__lt=high)
        .order_by()
        .values_list("status")
        .annotate(total=Count("id"))
    )
    return {status: counts.get(status, 0) for status in RequestStatus.values}


# The first delivery of each request submitted in the range (decision #6: rework doesn't reset the clock),
# then PostgreSQL's percentile_cont for the median. Parameterised: no values are formatted into the SQL.
_MEDIAN_TO_DELIVERY_SQL = """
    SELECT
        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM first_delivery.delivered_at - r.created_at)
        ) / 3600.0 AS median_hours,
        count(*) AS delivered
    FROM dataset_requests AS r
    CROSS JOIN LATERAL (
        SELECT min(e.changed_at) AS delivered_at
        FROM request_status_events AS e
        WHERE e.request_id = r.id AND e.to_status = %s
    ) AS first_delivery
    WHERE r.created_at >= %s AND r.created_at < %s AND first_delivery.delivered_at IS NOT NULL
"""


def median_hours_to_delivery(start: date, end: date) -> tuple[float | None, int]:
    low, high = _bounds(start, end)
    with connection.cursor() as cursor:
        cursor.execute(_MEDIAN_TO_DELIVERY_SQL, [RequestStatus.DELIVERED, low, high])
        median, delivered = cursor.fetchone()
    return (round(float(median), 2) if median is not None else None), delivered
