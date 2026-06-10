"""
One-time admin bootstrap.

Runs during deploy (called from build.sh). If BOOTSTRAP_ADMIN_EMAIL and
BOOTSTRAP_ADMIN_PASSWORD are set in the environment AND no superuser with that
email exists yet, it creates one. On every later deploy it sees the admin
already exists and does nothing. The password lives only in Render's
environment settings — never in code or GitHub.
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create an initial admin user from environment variables, once."

    def handle(self, *args, **options):
        User = get_user_model()
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "mVia Admin").strip()

        if not email or not password:
            self.stdout.write("bootstrap_admin: no admin env vars set; skipping.")
            return

        existing = User.objects.filter(email=email).first()
        if existing:
            # Make sure they have admin powers, but never touch the password.
            changed = False
            for attr in ("is_staff", "is_superuser", "is_email_verified", "is_active"):
                if not getattr(existing, attr):
                    setattr(existing, attr, True)
                    changed = True
            if changed:
                existing.save()
                self.stdout.write(f"bootstrap_admin: upgraded existing user {email} to admin.")
            else:
                self.stdout.write(f"bootstrap_admin: admin {email} already exists; nothing to do.")
            return

        User.objects.create_superuser(email=email, password=password, full_name=name)
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created admin {email}."))
