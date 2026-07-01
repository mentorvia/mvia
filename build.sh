#!/usr/bin/env bash
# This script runs on Render every time you deploy.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input

# One-time recovery: wipes the DB ONLY if CONFIRM_RESET_SCHEMA=yes-wipe-everything.
# Safe no-op otherwise. Remove the env var after the database is fixed.
python manage.py reset_schema

python manage.py migrate
# Seed the starter interest taxonomy (safe to run every deploy).
python manage.py seed_interests
# Create the admin account once, from environment variables (no-op if it exists).
python manage.py bootstrap_admin

# Compile translation files (.po -> .mo) so Kannada (and future languages) load.
# Try Django's compilemessages (needs gettext); if gettext isn't available on the
# build image, fall back to a pure-Python compile via polib.
python manage.py compilemessages -l kn || python compile_messages_fallback.py
