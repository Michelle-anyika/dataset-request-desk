"""Business dates. Timestamps are stored in UTC; rules about "today" use the company's time zone.

The company works on Kigali time (UTC+2). Between 00:00 and 02:00 there it is still yesterday in UTC, so a
deadline check based on the UTC date would accept a deadline that has already passed.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def business_date(moment: datetime) -> date:
    return moment.astimezone(ZoneInfo(settings.BUSINESS_TIME_ZONE)).date()


def business_today() -> date:
    return business_date(timezone.now())
