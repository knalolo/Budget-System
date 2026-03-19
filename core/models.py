"""
Core shared models for the procurement approval system.

Provides:
- FileAttachment  – generic file attachment via GenericForeignKey
- SystemConfig    – key-value configuration store (JSON-encoded values)
- EmailNotificationLog – audit log of all outbound notification emails
"""
import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from django.conf import settings as django_settings

User = get_user_model()


# ---------------------------------------------------------------------------
# FileAttachment
# ---------------------------------------------------------------------------

class FileAttachment(models.Model):
    """Generic file attachment that can be linked to any model instance."""

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="file_attachments",
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    file = models.FileField(upload_to="attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(
        max_length=50,
        choices=django_settings.FILE_TYPE_CHOICES,
    )
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_file_type_display()})"


# ---------------------------------------------------------------------------
# SystemConfig
# ---------------------------------------------------------------------------

class SystemConfig(models.Model):
    """Key-value configuration store with JSON-encoded values."""

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(help_text="JSON-encoded value")
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "System Config"
        verbose_name_plural = "System Config"

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_value(cls, key: str, default=None):
        """Return the parsed JSON value for *key*, or *default* if not found."""
        try:
            record = cls.objects.get(key=key)
            return json.loads(record.value)
        except cls.DoesNotExist:
            return default
        except (json.JSONDecodeError, ValueError):
            return default

    @classmethod
    def set_value(cls, key: str, value, description: str = "") -> "SystemConfig":
        """Persist *value* (serialised to JSON) under *key*. Returns the instance."""
        encoded = json.dumps(value)
        instance, _ = cls.objects.update_or_create(
            key=key,
            defaults={"value": encoded, "description": description},
        )
        return instance


# ---------------------------------------------------------------------------
# EmailNotificationLog
# ---------------------------------------------------------------------------

_EMAIL_STATUS_PENDING = "pending"
_EMAIL_STATUS_SENT = "sent"
_EMAIL_STATUS_FAILED = "failed"

EMAIL_STATUS_CHOICES = [
    (_EMAIL_STATUS_PENDING, "Pending"),
    (_EMAIL_STATUS_SENT, "Sent"),
    (_EMAIL_STATUS_FAILED, "Failed"),
]


class EmailNotificationLog(models.Model):
    """Audit log of every outbound notification email attempted by the system."""

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_notification_logs",
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    recipients = models.JSONField(
        default=list,
        help_text="List of primary recipient email addresses",
    )
    cc_recipients = models.JSONField(
        default=list,
        help_text="List of CC recipient email addresses",
    )
    subject = models.CharField(max_length=500)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=EMAIL_STATUS_CHOICES,
        default=_EMAIL_STATUS_PENDING,
    )
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        recipients_preview = ", ".join(self.recipients[:2])
        return f"[{self.status}] {self.subject} -> {recipients_preview}"
