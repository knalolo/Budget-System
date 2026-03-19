"""URL configuration for the custom admin panel."""
from django.urls import path
from django.views.generic import RedirectView

from accounts.admin_panel_views import (
    AuditLogsView,
    SystemConfigView,
    UserManagementView,
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
    path("config/", SystemConfigView.as_view(), name="admin-config"),
    path("logs/", AuditLogsView.as_view(), name="admin-logs"),
    path(
        "users/<int:pk>/update-role/",
        update_user_role,
        name="admin-update-role",
    ),
    path("config/update/", update_config, name="admin-update-config"),
]
