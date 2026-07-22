"""
Django admin registrations for core models.
"""
from django.contrib import admin

from core.models import (
    EmailOutbox,
    FileAttachment,
    SystemConfig,
)


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "file_type", "file_size", "uploaded_by", "created_at")
    list_filter = ("file_type",)
    search_fields = ("original_filename", "uploaded_by__username")
    readonly_fields = ("content_type", "object_id", "file_size", "created_at")
    ordering = ("-created_at",)


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description")
    search_fields = ("key", "description")
    ordering = ("key",)


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("subject", "status", "to_emails", "attempts", "processed_at", "created_at")
    list_filter = ("status", "event_type")
    search_fields = ("subject", "to_emails", "cc_emails", "event_key")
    readonly_fields = ("attempts", "last_error", "processed_at", "created_at", "updated_at")
    ordering = ("-created_at",)
