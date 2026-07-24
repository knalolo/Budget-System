"""Django admin registrations for the orders app."""

from django.contrib import admin

from .models import (
    ExpenseCategory,
    Project,
    ProjectAnnualBudget,
    PurchaseRequest,
    PurchaseRequestLineItem,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["mc_number", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["mc_number", "name"]
    ordering = ["mc_number"]


@admin.register(ProjectAnnualBudget)
class ProjectAnnualBudgetAdmin(admin.ModelAdmin):
    list_display = [
        "fiscal_year",
        "project",
        "amount_sgd",
        "status",
        "updated_by",
        "updated_at",
    ]
    list_filter = ["fiscal_year", "status"]
    search_fields = ["project__mc_number", "project__name"]
    ordering = ["-fiscal_year", "project__mc_number"]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]


class PurchaseRequestLineItemInline(admin.TabularInline):
    model = PurchaseRequestLineItem
    extra = 0


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = [
        "workflow_number_display",
        "requester",
        "vendor",
        "currency",
        "total_price",
        "status",
        "created_at",
    ]
    list_filter = ["status", "currency", "project", "expense_category"]
    search_fields = ["request_number", "description", "vendor"]
    readonly_fields = ["workflow_number_display", "created_at", "updated_at"]
    exclude = ["request_number"]
    inlines = [PurchaseRequestLineItemInline]

    @admin.display(description="Request No.")
    def workflow_number_display(self, obj):
        return obj.workflow_number
