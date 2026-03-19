"""API URL configuration for email log endpoints."""
from django.urls import path

from core.config_api import EmailLogListView

urlpatterns = [
    path("", EmailLogListView.as_view(), name="api-email-logs-list"),
]
