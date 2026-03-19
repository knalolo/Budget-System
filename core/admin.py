from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Project, CostItem, ProjectBudget, PORequest, ApprovalLog, UserProfile


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_code", "project_name", "project_manager", "status", "start_date", "end_date")
    search_fields = ("project_code", "project_name", "project_manager", "project_owner")
    list_filter = ("status",)


@admin.register(CostItem)
class CostItemAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(ProjectBudget)
class ProjectBudgetAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "cost_item",
        "internal_hours",
        "internal_cost",
        "external_cost",
        "approved_budget",
        "actual_spent",
        "remaining_budget",
    )
    list_filter = ("project", "cost_item")
    search_fields = ("project__project_code", "project__project_name", "cost_item__name")


@admin.register(PORequest)
class PORequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_no",
        "project",
        "cost_item",
        "requester_name",
        "supplier_name",
        "amount",
        "currency",
        "status",
        "over_budget_flag",
        "request_date",
    )
    list_filter = ("status", "currency", "over_budget_flag", "project", "cost_item")
    search_fields = ("request_no", "requester_name", "supplier_name", "description")


@admin.register(ApprovalLog)
class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ("po_request", "action", "action_by", "created_at")
    list_filter = ("action",)
    search_fields = ("po_request__request_no", "action_by", "comment")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("name", "email")