"""
Template-based authentication views for the accounts app.

SSO (Azure AD / MSAL) integration is handled in a later phase.
For now:
  - login_view   – renders the login page; POST stub for Azure AD redirect.
  - logout_view  – logs out the current user and redirects.
  - dev_login_view – development-only view to log in as any existing user.
"""
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render


def login_view(request: HttpRequest) -> HttpResponse:
    """
    GET  – Render the login page.
    POST – Placeholder: will redirect to Azure AD OAuth flow once SSO is wired.
           For now, returns to the login page with an informational message.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        # Phase 4A will replace this stub with the actual MSAL redirect.
        messages.info(request, "Microsoft 365 SSO is not yet configured. Use the dev login during development.")
        return redirect("accounts:login")

    return render(request, "auth/login.html")


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out the current user and redirect to the login page."""
    auth.logout(request)
    messages.success(request, "You have been signed out.")
    return redirect(settings.LOGOUT_REDIRECT_URL)


def dev_login_view(request: HttpRequest) -> HttpResponse:
    """
    Development-only view that lets a developer log in as any existing user.

    This view is only accessible when ``DEBUG=True``; all other requests
    receive a 403 Forbidden response.
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
