"""Admin registration for the payments app."""
from django.contrib import admin

from .models import PaymentRelease


@admin.register(PaymentRelease)
class PaymentReleaseAdmin(admin.ModelAdmin):
    list_display = [
        "request_number",
        "vendor",
        "requester",
        "project",
        "currency",
        "total_price",
        "status",
        "created_at",
    ]
    list_filter = ["status", "currency", "project"]
    search_fields = ["request_number", "vendor", "requester__username", "description"]
    readonly_fields = [
        "request_number",
        "created_at",
        "updated_at",
        "pcm_decided_at",
        "final_decided_at",
    ]
    fieldsets = [
        (
            "Identity",
            {"fields": ["request_number", "purchase_request", "requester"]},
        ),
        (
            "Request Details",
            {
                "fields": [
                    "expense_category",
                    "project",
                    "description",
                    "vendor",
                    "currency",
                    "total_price",
                    "justification",
                    "po_number",
                    "target_payment",
                ]
            },
        ),
        (
            "Workflow",
            {"fields": ["status"]},
        ),
        (
            "PCM Approval",
            {
                "fields": [
                    "pcm_approver",
                    "pcm_decision",
                    "pcm_comment",
                    "pcm_decided_at",
                ]
            },
        ),
        (
            "Final Approval",
            {
                "fields": [
                    "final_approver",
                    "final_decision",
                    "final_comment",
                    "final_decided_at",
                ]
            },
        ),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"]},
        ),
    ]
