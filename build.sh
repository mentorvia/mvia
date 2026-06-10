#!/usr/bin/env bash
# This script runs on Render every time you deploy.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Create the admin account once, from environment variables (does nothing if it already exists).
python manage.py bootstrap_admin
