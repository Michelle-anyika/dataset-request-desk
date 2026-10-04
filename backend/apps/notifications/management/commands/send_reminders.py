from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.reminders import send_reminders


class Command(BaseCommand):
    help = "Reminders, escalations, deadline warnings and pending emails. Safe to run every minute."

    def handle(self, *args, **options):
        report = send_reminders(now=timezone.now())
        # Housekeeping: blacklist rows for refresh tokens that have expired anyway (docs/security.md §3).
        call_command("flushexpiredtokens", verbosity=0)
        call_command("purge_idempotency_keys", verbosity=0)
        self.stdout.write(
            f"{report.reminders} reminders, {report.escalations} escalations, "
            f"{report.deadline_warnings} deadline warnings, {report.emails_sent} emails sent."
        )
