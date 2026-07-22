"""
Core shared models for the procurement approval system.

Provides:
- FileAttachment  – generic file attachment via GenericForeignKey
- SystemConfig    – key-value configuration store (JSON-encoded values)
- EmailOutbox – workflow email queue processed by the local Outlook worker
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
# EmailOutbox
# ---------------------------------------------------------------------------

class EmailOutbox(models.Model):
    """Queue of emails waiting for the local Outlook desktop worker."""

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DRAFTED = "drafted"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DRAFTED, "Drafted"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    event_type = models.CharField(max_length=100, blank=True)
    event_key = models.CharField(max_length=200, blank=True, db_index=True)
    from_mailbox = models.EmailField(default="SGRDPR@WAGO.com")
    to_emails = models.TextField(help_text="Semicolon-separated recipient email addresses.")
    cc_emails = models.TextField(blank=True, help_text="Semicolon-separated CC email addresses.")
    subject = models.CharField(max_length=255)
    body_html = models.TextField()
    attachment_paths = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_type", "event_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "event_key"],
                condition=~models.Q(event_key=""),
                name="unique_outbox_workflow_event",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.status}] {self.subject} -> {self.to_emails}"
