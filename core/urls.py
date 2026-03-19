"""URL configuration for the core app (dashboard, home views)."""
from django.urls import path

from .views import DashboardView

app_name = "core"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
