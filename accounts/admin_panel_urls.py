"""URL configuration for the custom admin panel."""
from django.urls import path
from django.views.generic import RedirectView

from accounts.admin_panel_views import (
    AuditLogsView,
    SystemConfigView,
    UserManagementView,
    create_user,
    delete_project,
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
    path("config/update/", update_config, name="admin-update-config"),
    path("config/projects/new/", save_project, name="admin-project-create"),
    path("config/projects/<int:pk>/save/", save_project, name="admin-project-save"),
    path("config/projects/<int:pk>/delete/", delete_project, name="admin-project-delete"),
]
