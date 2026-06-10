"""
DANGER TOOL — wipes ALL database tables, then exits. Use only to recover from a
broken/empty database during early setup.

SAFETY: does nothing unless the environment variable CONFIRM_RESET_SCHEMA is set
to exactly "yes-wipe-everything". This makes accidental data loss essentially
impossible — you have to deliberately set that value, and remove it afterward.

It drops and recreates the PostgreSQL "public" schema (or, on SQLite locally,
deletes the file's tables), which clears the inconsistent migration history so
the next migrate rebuilds everything in the correct order.
"""

import os
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Wipe all tables (guarded by CONFIRM_RESET_SCHEMA env var)."

    def handle(self, *args, **options):
        confirm = os.environ.get("CONFIRM_RESET_SCHEMA", "")
        if confirm != "yes-wipe-everything":
            self.stdout.write("reset_schema: not confirmed; skipping (this is the safe default).")
            return

        vendor = connection.vendor
        with connection.cursor() as cursor:
            if vendor == "postgresql":
                self.stdout.write(self.style.WARNING("reset_schema: dropping and recreating public schema..."))
                cursor.execute("DROP SCHEMA public CASCADE;")
                cursor.execute("CREATE SCHEMA public;")
                # Restore default privileges so Django can recreate tables.
                cursor.execute("GRANT ALL ON SCHEMA public TO public;")
            elif vendor == "sqlite":
                self.stdout.write(self.style.WARNING("reset_schema: dropping all SQLite tables..."))
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [row[0] for row in cursor.fetchall()]
                cursor.execute("PRAGMA foreign_keys=OFF;")
                for t in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS "{t}";')
                cursor.execute("PRAGMA foreign_keys=ON;")
            else:
                self.stderr.write(f"reset_schema: unsupported database vendor '{vendor}'.")
                return
        self.stdout.write(self.style.SUCCESS("reset_schema: database wiped. Next migrate will rebuild it."))
