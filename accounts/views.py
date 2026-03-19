"""
Template-based authentication views for the accounts app.

SSO flow:
  - login_view      – GET renders the login page; POST initiates Azure AD redirect.
  - callback_view   – Handles the Azure AD OAuth2 callback.
  - logout_view     – Clears the Django session and redirects.
  - dev_login_view  – Development-only shortcut to log in as any existing user.
"""
import logging
import urllib.parse

from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.auth_service import get_auth_url, process_auth_callback

logger = logging.getLogger(__name__)


def login_view(request: HttpRequest) -> HttpResponse:
    """
    GET  – Render the login page.
    POST – Initiate the Azure AD authorization flow by redirecting to MSAL auth URL.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        try:
            auth_url = get_auth_url(request)
            return redirect(auth_url)
        except ValueError as exc:
            logger.warning("Azure AD not configured: %s", exc)
            messages.error(
                request,
                "Microsoft 365 SSO is not configured. "
                "Contact an administrator or use the developer login.",
            )
            return redirect("accounts:login")

    return render(request, "auth/login.html")


def callback_view(request: HttpRequest) -> HttpResponse:
    """
    Handle the Azure AD OAuth2 callback.

    Azure AD redirects here after the user authenticates. Validates the state
    parameter, exchanges the authorization code for tokens, fetches the user's
    profile from Microsoft Graph, and logs the user into Django.
    """
    try:
        user = process_auth_callback(request)
    except (ValueError, RuntimeError) as exc:
        logger.error("SSO callback failed: %s", exc)
        messages.error(request, f"Sign-in failed: {exc}")
        return redirect("accounts:login")

    auth.login(request, user)
    messages.success(request, f"Welcome, {user.first_name or user.username}!")
    return redirect(settings.LOGIN_REDIRECT_URL)


def logout_view(request: HttpRequest) -> HttpResponse:
    """
    Log out the current user.

    Clears the Django session and, if Azure AD is configured, redirects to the
    Azure AD logout endpoint so the Microsoft session is also terminated.
    """
    auth.logout(request)

    tenant_id = getattr(settings, "AZURE_AD_TENANT_ID", "")
    if tenant_id:
        post_logout_redirect = request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)
        logout_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={urllib.parse.quote(post_logout_redirect, safe='')}"
        )
        return redirect(logout_url)

    messages.success(request, "You have been signed out.")
    return redirect(settings.LOGOUT_REDIRECT_URL)


def dev_login_view(request: HttpRequest) -> HttpResponse:
    """
    Development-only view that lets a developer log in as any existing user.

    Only accessible when DEBUG=True; all other requests receive 403 Forbidden.
    """
    if not settings.DEBUG:
        return HttpResponseForbidden("This view is only available in DEBUG mode.")

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        if not user_id:
            messages.error(request, "No user selected.")
            return redirect("accounts:dev-login")

        user = get_object_or_404(User, pk=user_id)
        # Use the model-backend explicitly so we don't need a password.
        user.backend = "django.contrib.auth.backends.ModelBackend"
        auth.login(request, user)
        messages.success(request, f"Logged in as {user.username}.")
        return redirect(settings.LOGIN_REDIRECT_URL)

    users = User.objects.select_related("profile").order_by("username")
    return render(request, "auth/login.html", {"dev_users": users})
