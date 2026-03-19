"""
Production settings.

Extends base settings with production-specific overrides:
- DEBUG disabled
- PostgreSQL database from environment
- ALLOWED_HOSTS from environment
- SMTP email backend
- Security hardening
"""
import os

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = False

# Validate that a proper secret key is configured in production
if not SECRET_KEY:  # noqa: F821 — defined by base.py wildcard import
    raise ValueError("SECRET_KEY environment variable must be set in production.")

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

# ---------------------------------------------------------------------------
# Database — PostgreSQL
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# ---------------------------------------------------------------------------
# Email — SMTP
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# CORS — explicit origins only
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = False
