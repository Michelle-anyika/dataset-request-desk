from django.core.management.base import BaseCommand

from apps.core.idempotency import purge_expired


class Command(BaseCommand):
    help = "Delete idempotency keys older than a day. Run by the scheduler."

    def handle(self, *args, **options):
        deleted = purge_expired()
        if options["verbosity"]:
            self.stdout.write(f"{deleted} expired idempotency keys deleted.")
