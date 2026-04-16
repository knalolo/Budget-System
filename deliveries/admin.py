"""Admin configuration for the deliveries app."""

from django.contrib import admin

from .models import DeliverySubmission, DeliverySubmissionLineItem


class DeliverySubmissionLineItemInline(admin.TabularInline):
    model = DeliverySubmissionLineItem
    extra = 0


@admin.register(DeliverySubmission)
class DeliverySubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "request_number",
        "requester",
        "vendor",
        "currency",
        "total_price",
        "status",
        "created_at",
    ]
    list_filter = ["status", "currency", "created_at"]
    search_fields = ["request_number", "vendor", "requester__username"]
    readonly_fields = ["request_number", "created_at", "updated_at"]
    ordering = ["-created_at"]
    inlines = [DeliverySubmissionLineItemInline]
