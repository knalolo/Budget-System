"""
Base Django settings for the procurement approval system.

All environment-specific settings files (development.py, production.py)
import from this module and override as needed.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

# Raises KeyError in production if not set; development.py overrides this
# with a safe fallback before the check can fire.
_secret_key = os.environ.get("SECRET_KEY")
if _secret_key is None:
    # Allow environment-specific settings to set SECRET_KEY themselves.
    # Production settings will raise at startup if this remains unset.
    SECRET_KEY = ""
else:
    SECRET_KEY = _secret_key

ALLOWED_HOSTS: list[str] = []

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
]

LOCAL_APPS = [
    "accounts",
    "core",
    "orders",
    "payments",
    "deliveries",
    "approvals",
    "assets",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.ForceEnglishMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.LoginRequiredMiddleware",
]

# ---------------------------------------------------------------------------
# URL configuration
# ---------------------------------------------------------------------------

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# WSGI / ASGI
# ---------------------------------------------------------------------------

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "auth.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# File upload limits (1 GB)
# ---------------------------------------------------------------------------

DATA_UPLOAD_MAX_MEMORY_SIZE = 1_073_741_824   # 1 GB in bytes
FILE_UPLOAD_MAX_MEMORY_SIZE = 1_073_741_824   # 1 GB in bytes

# ---------------------------------------------------------------------------
# Default auto field
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS: list[str] = []

# ---------------------------------------------------------------------------
# Azure AD / MSAL settings
# ---------------------------------------------------------------------------

AZURE_AD_TENANT_ID = os.environ.get("AZURE_AD_TENANT_ID", "")
AZURE_AD_CLIENT_ID = os.environ.get("AZURE_AD_CLIENT_ID", "")
AZURE_AD_CLIENT_SECRET = os.environ.get("AZURE_AD_CLIENT_SECRET", "")
AZURE_AD_REDIRECT_URI = os.environ.get("AZURE_AD_REDIRECT_URI", "http://localhost:8000/auth/callback/")
AZURE_AD_SCOPES = ["User.Read"]

# ---------------------------------------------------------------------------
# Email settings
# ---------------------------------------------------------------------------

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.office365.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

CURRENCY_CHOICES = [
    ("SGD", "SG$"),
    ("USD", "US$"),
    ("EUR", "EUR"),
]

DEFAULT_CURRENCY = "SGD"

# Purchase Request statuses
PR_STATUS_DRAFT = "draft"
PR_STATUS_PENDING_PCM = "pending_pcm"
PR_STATUS_PENDING_FINAL = "pending_final"
PR_STATUS_APPROVED = "approved"
PR_STATUS_REJECTED = "rejected"
PR_STATUS_PO_SENT = "po_sent"
PR_STATUS_ORDERED = "ordered"
PR_STATUS_COMPLETED = "completed"

PR_STATUS_CHOICES = [
    (PR_STATUS_DRAFT, "Draft"),
    (PR_STATUS_PENDING_PCM, "Pending PCM Review"),
    (PR_STATUS_PENDING_FINAL, "Pending Final Review"),
    (PR_STATUS_APPROVED, "Approved"),
    (PR_STATUS_REJECTED, "Rejected"),
    (PR_STATUS_PO_SENT, "PO Sent"),
    (PR_STATUS_ORDERED, "Ordered"),
    (PR_STATUS_COMPLETED, "Completed"),
]

# Payment Release statuses
PAYMENT_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("pending_pcm", "Pending PCM Review"),
    ("pending_final", "Pending Final Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

# Delivery Submission statuses
DELIVERY_STATUS_CHOICES = [
    ("submitted", "Submitted"),
    ("saved", "Saved"),
]

# Approval decision choices
DECISION_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

# User roles
ROLE_REQUESTER = "requester"
ROLE_PCM_APPROVER = "pcm_approver"
ROLE_FINAL_APPROVER = "final_approver"
ROLE_ADMIN = "admin"

ROLE_CHOICES = [
    (ROLE_REQUESTER, "Requester"),
    (ROLE_PCM_APPROVER, "PCM Approver"),
    (ROLE_FINAL_APPROVER, "Final Approver"),
    (ROLE_ADMIN, "Admin"),
]

# File type choices
FILE_TYPE_CHOICES = [
    ("quotation", "Quotation"),
    ("new_order_list", "New Order List"),
    ("invoice", "Invoice"),
    ("proforma_invoice", "Proforma Invoice"),
    ("delivery_order", "Delivery Order"),
    ("sales_order", "Sales Order"),
    ("po_document", "PO Document"),
    ("other", "Other"),
]

# Allowed file extensions
ALLOWED_FILE_EXTENSIONS = [
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".mp4", ".avi", ".mov", ".mp3", ".wav",
]

MAX_FILES_PER_REQUEST = 10
MAX_FILE_SIZE_BYTES = 1_073_741_824  # 1 GB
