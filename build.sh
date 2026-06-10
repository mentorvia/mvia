#!/usr/bin/env bash
# This script runs on Render every time you deploy.
# It installs dependencies, collects static files, and applies database changes.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
