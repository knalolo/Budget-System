"""Django admin registrations for the orders app."""

from django.contrib import admin

from .models import ExpenseCategory, Project


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
