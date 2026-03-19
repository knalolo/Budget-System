"""API URL configuration for dashboard data endpoints."""
from django.urls import path

from .dashboard_api import DashboardSummaryView, MyRequestsView, PendingApprovalsView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("my-requests/", MyRequestsView.as_view(), name="dashboard-my-requests"),
    path("pending-approvals/", PendingApprovalsView.as_view(), name="dashboard-pending-approvals"),
]
