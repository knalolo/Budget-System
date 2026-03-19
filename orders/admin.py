"""Django admin registrations for the orders app."""

from django.contrib import admin

from .models import ExpenseCategory, Project, PurchaseRequest


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["mc_number", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["mc_number", "name"]
    ordering = ["mc_number"]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = [
        "request_number",
        "requester",
        "vendor",
        "currency",
        "total_price",
        "status",
        "created_at",
    ]
    list_filter = ["status", "currency", "project", "expense_category"]
    search_fields = ["request_number", "description", "vendor"]
    readonly_fields = ["request_number", "created_at", "updated_at"]
