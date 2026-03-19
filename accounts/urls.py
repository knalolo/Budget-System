"""URL configuration for the accounts app (authentication views)."""
from django.conf import settings
from django.urls import path

from accounts.views import callback_view, dev_login_view, login_view, logout_view

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("callback/", callback_view, name="auth-callback"),
    path("logout/", logout_view, name="logout"),
]

if settings.DEBUG:
    urlpatterns += [
        path("dev-login/", dev_login_view, name="dev-login"),
    ]
