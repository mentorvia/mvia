"""
Runs mVia's scheduled maintenance tasks:
  - expire stale unpaid bookings (frees the slot)
  - auto-complete sessions whose time has passed (feeds payouts + reviews)
  - send 24h and 1h reminder emails for upcoming sessions

Safe to run repeatedly (idempotent). Intended to be called on a schedule by a
Render Cron Job, e.g. every 15 minutes:

    python manage.py run_scheduled_tasks
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.services import run_scheduled_tasks


class Command(BaseCommand):
    help = "Run scheduled maintenance: expire unpaid, auto-complete past sessions, send reminders."

    def handle(self, *args, **options):
        started = timezone.now()
        result = run_scheduled_tasks()
        self.stdout.write(self.style.SUCCESS(
            f"[{started:%Y-%m-%d %H:%M:%S}] scheduled tasks done: "
            f"expired_unpaid={result['expired_unpaid']}, "
            f"auto_completed={result['auto_completed']}, "
            f"reminders_24h={result['reminders_24h']}, "
            f"reminders_1h={result['reminders_1h']}"
        ))
