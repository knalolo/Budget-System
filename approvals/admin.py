"""
Django admin configuration for the approvals app.
"""
from django.contrib import admin

from .models import ApprovalLog


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    """Read-only admin for ApprovalLog audit records."""

    list_display = [
        "id",
        "content_type",
        "object_id",
        "action",
        "action_by",
        "old_status",
        "new_status",
        "created_at",
    ]
    list_filter = ["action", "content_type", "created_at"]
    search_fields = ["action_by__username", "action_by__email", "comment"]
    readonly_fields = [
        "content_type",
        "object_id",
        "content_object",
        "action",
        "action_by",
        "comment",
        "old_status",
        "new_status",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        """Approval logs are created programmatically only."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Approval logs are immutable."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Approval logs must not be deleted via admin."""
        return False
