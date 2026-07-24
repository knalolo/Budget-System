"""URL configuration for the custom admin panel."""
from django.urls import path
from django.views.generic import RedirectView

from accounts.admin_panel_views import (
    AuditLogsView,
    SystemConfigView,
    UserManagementView,
    copy_annual_budgets,
    create_user,
    delete_project,
    reset_user_password,
    save_annual_budget,
    save_project,
    update_config,
    update_user_role,
)

app_name = "admin-panel"

urlpatterns = [
    path(
        "",
        RedirectView.as_view(pattern_name="admin-panel:admin-users", permanent=False),
        name="admin-index",
    ),
    path("users/", UserManagementView.as_view(), name="admin-users"),
    path("users/new/", create_user, name="admin-user-create"),
    path("config/", SystemConfigView.as_view(), name="admin-config"),
    path("logs/", AuditLogsView.as_view(), name="admin-logs"),
    path(
        "users/<int:pk>/update-role/",
        update_user_role,
        name="admin-update-role",
    ),
    path(
        "users/<int:pk>/reset-password/",
        reset_user_password,
        name="admin-reset-password",
    ),
    path("config/update/", update_config, name="admin-update-config"),
    path("config/projects/new/", save_project, name="admin-project-create"),
    path("config/projects/<int:pk>/save/", save_project, name="admin-project-save"),
    path("config/projects/<int:pk>/delete/", delete_project, name="admin-project-delete"),
    path(
        "config/budgets/save/",
        save_annual_budget,
        name="admin-budget-save",
    ),
    path(
        "config/budgets/copy/",
        copy_annual_budgets,
        name="admin-budget-copy",
    ),
]
