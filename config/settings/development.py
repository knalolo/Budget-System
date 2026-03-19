"""
Development settings.

Extends base settings with development-specific overrides:
- DEBUG enabled
- SQLite database (no external dependency)
- All hosts allowed
- Console email backend
- Additional debugging tools
"""
import os
from pathlib import Path

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Provide a default SECRET_KEY so `manage.py check` works without a .env file.
# Override this by setting SECRET_KEY in your .env file.
if not SECRET_KEY:  # noqa: F821 — defined by base.py wildcard import
    SECRET_KEY = "dev-insecure-secret-key-change-in-production-do-not-use"  # noqa: S105

# ---------------------------------------------------------------------------
# Database — SQLite for zero-config local development
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------------------
# Email — print to console
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# CORS — allow everything in development
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Django REST Framework — browsable API in development
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    **globals().get("REST_FRAMEWORK", {}),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
