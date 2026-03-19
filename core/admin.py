"""
Django admin registrations for core models.
"""
from django.contrib import admin

from core.models import EmailNotificationLog, FileAttachment, SystemConfig


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


@admin.register(EmailNotificationLog)
class EmailNotificationLogAdmin(admin.ModelAdmin):
    list_display = ("subject", "status", "recipients_preview", "sent_at", "created_at")
    list_filter = ("status",)
    search_fields = ("subject", "recipients")
    readonly_fields = (
        "content_type",
        "object_id",
        "recipients",
        "cc_recipients",
        "subject",
        "body",
        "status",
        "error_message",
        "sent_at",
        "created_at",
    )
    ordering = ("-created_at",)

    @admin.display(description="Recipients")
    def recipients_preview(self, obj):
        recipients = obj.recipients or []
        preview = ", ".join(recipients[:2])
        if len(recipients) > 2:
            preview += f" (+{len(recipients) - 2} more)"
        return preview
