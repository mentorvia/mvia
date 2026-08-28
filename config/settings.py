"""
Django settings for the mVia platform.

This file reads its configuration from environment variables so the SAME code
runs safely on your laptop AND on Render, without secrets ever living in the code.
Anything sensitive (passwords, API keys) comes from the environment, never from here.
"""

from pathlib import Path
import os

import dj_database_url

# BASE_DIR is the project's root folder (where manage.py lives).
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Load a local .env file if present (for local development only) ---
# On Render, real environment variables are set in the dashboard instead.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def env(key, default=None):
    """Small helper: read an environment variable, with an optional fallback."""
    return os.environ.get(key, default)


# --- Core security settings ---

# SECRET_KEY signs cookies and sessions. It MUST be secret in production.
# Locally we fall back to an obviously-insecure value so the app still runs.
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-local-key-change-me")

# DEBUG shows detailed error pages. Great locally, DANGEROUS in production.
# It is ON only if DJANGO_DEBUG is explicitly "true".
DEBUG = env("DJANGO_DEBUG", "true").lower() == "true"

# ALLOWED_HOSTS lists the domains allowed to serve this app.
# Render provides RENDER_EXTERNAL_HOSTNAME automatically.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".onrender.com"]
_render_host = env("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
# Your future custom domains (safe to leave here now):
ALLOWED_HOSTS += ["mvia.in", "www.mvia.in", "staging.mvia.in"]

# CSRF trusted origins (needed once we're on https domains).
CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
    "https://mvia.in",
    "https://www.mvia.in",
    "https://staging.mvia.in",
]


# --- Installed apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Our own apps:
    "accounts",
    "core",
    "dashboard",
    "interests",
    "profiles",
    "auditlog",
    "directory",
    "bookings",
    "payments",
    "reviews",
]

# Use our email-based User model instead of Django's default.
AUTH_USER_MODEL = "accounts.User"

# Where @login_required sends people, and where login/logout land.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves CSS/JS efficiently in production (added right after security).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware enables per-request language selection (must sit after
    # SessionMiddleware and before CommonMiddleware).
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.NoCacheForAuthenticatedMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.staff_badges",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database ---
# Locally (no DATABASE_URL set) we use a simple SQLite file so you need ZERO setup.
# On Render, DATABASE_URL points at PostgreSQL and this picks it up automatically.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=bool(env("DATABASE_URL")),
    )
}


# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization ---
LANGUAGE_CODE = "en-us"

# Languages offered in the site's language dropdown. English default; Kannada
# added now, with room to add Hindi/Tamil etc. later by adding to this list and
# providing a translation file.
from django.utils.translation import gettext_lazy as _gl  # noqa: E402
LANGUAGES = [
    ("en", _gl("English")),
    # ("kn", _gl("ಕನ್ನಡ")),  # Kannada — hidden until translation is complete (re-enable in ~1 month)
]

# Where Django looks for translation (.po/.mo) files.
LOCALE_PATHS = [BASE_DIR / "locale"]
# India-first launch: times shown in Indian Standard Time.
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Currency for the whole platform (India-first launch).
CURRENCY_CODE = "INR"
CURRENCY_SYMBOL = "\u20b9"  # ₹

# Platform fee: mVia's commission, ADDED on top of the mentor's rate.
# e.g. 0.20 means a ₹2000 mentor session costs the mentee ₹2400; mVia keeps ₹400.
PLATFORM_FEE_RATE = float(env("PLATFORM_FEE_RATE", "0.20"))

# How long an unpaid (pending_payment) booking is held before the scheduler
# expires it and frees the slot. Minutes.
BOOKING_EXPIRY_MINUTES = int(env("BOOKING_EXPIRY_MINUTES", "30"))

# Availability model: fixed session length and how far ahead mentees can book.
SESSION_LENGTH_MINUTES = int(env("SESSION_LENGTH_MINUTES", "60"))
BOOKING_WINDOW_DAYS = int(env("BOOKING_WINDOW_DAYS", "14"))


# --- Static files (CSS, JavaScript, images) ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Project-level static assets (brand images, etc.) live here and get collected.
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media (user-uploaded files, e.g. mentor photos).
# MEDIA_ROOT points to a persistent location. On Render (paid), attach a disk
# and set MEDIA_ROOT to its mount path (e.g. /var/data/media) so uploads survive
# redeploys. Locally it defaults to a "media" folder in the project.
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", str(BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Production security hardening (only active when DEBUG is off) ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# --- Third-party services: PLACEHOLDERS for now ---
# These read from the environment but are not active until you add real keys later.
# The code will check "is this configured?" and stay in safe test/no-op mode if not.

# Razorpay (payments) — test mode during build, live after KYC.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_ENABLED = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")

# SendGrid (email) — sender is hello@mvia.in per the requirements.
SENDGRID_API_KEY = env("SENDGRID_API_KEY", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "info@mvia.in")
SENDGRID_ENABLED = bool(SENDGRID_API_KEY)

# Resend email provider. When RESEND_API_KEY is set, real emails send via Resend.
# Sender must be at a domain verified in your Resend account (e.g. info@mvia.in).
RESEND_API_KEY = env("RESEND_API_KEY", "")
RESEND_ENABLED = bool(RESEND_API_KEY)

# Platform fee (admin-configurable later; this is just the starting default, in rupees).
DEFAULT_PLATFORM_FEE = env("DEFAULT_PLATFORM_FEE", "100")
