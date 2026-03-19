"""API URL configuration for system configuration endpoints."""
from django.urls import path

from core.config_api import SystemConfigListView

urlpatterns = [
    path("", SystemConfigListView.as_view(), name="api-config-list"),
]
