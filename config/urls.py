"""
Root URL configuration for the procurement approval system.
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("accounts.urls")),
    path(
        "api/v1/",
        include(
            [
                path("auth/", include("accounts.api_urls")),
                path("purchase-requests/", include("orders.api_urls")),
                path("payment-releases/", include("payments.api_urls")),
                path("delivery-submissions/", include("deliveries.api_urls")),
                path("attachments/", include("core.api_urls")),
                path("projects/", include("orders.api_urls_projects")),
                path("expense-categories/", include("orders.api_urls_categories")),
                path("asset-registrations/", include("assets.api_urls")),
                path("approval-logs/", include("approvals.api_urls")),
                path("config/", include("core.api_urls_config")),
                path("users/", include("accounts.api_urls_users")),
                path("email-logs/", include("core.api_urls_email_logs")),
                path("dashboard/", include("core.api_urls_dashboard")),
            ]
        ),
    ),
    path("purchase-requests/", include("orders.urls")),
    path("payment-releases/", include("payments.urls")),
    path("delivery-submissions/", include("deliveries.urls")),
    path("assets/", include("assets.urls")),
    path("admin-panel/", include("accounts.admin_panel_urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
