"""API URL configuration for accounts authentication endpoints."""
from django.urls import path

from accounts.api_views import MeView, TokenView

urlpatterns = [
    path("me/", MeView.as_view(), name="auth-me"),
    path("token/", TokenView.as_view(), name="auth-token"),
]
