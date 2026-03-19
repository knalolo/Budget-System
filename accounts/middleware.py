"""
LoginRequiredMiddleware – enforce authentication for all non-exempt paths.

Exempt paths (no redirect applied):
  - /auth/login/
  - /auth/callback/
  - /auth/logout/
  - /api/       (all API endpoints use DRF authentication)
  - /admin/     (Django admin has its own auth)
  - /static/
  - /media/
"""
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

# Paths that do not require an authenticated session.
_EXEMPT_PREFIXES = (
    "/auth/login/",
    "/auth/callback/",
    "/auth/logout/",
    "/api/",
    "/admin/",
    "/static/",
    "/media/",
)


class LoginRequiredMiddleware:
    """
    Redirect unauthenticated users to the login page for all non-exempt paths.

    Add to settings.MIDDLEWARE after AuthenticationMiddleware:
        "accounts.middleware.LoginRequiredMiddleware"
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self._is_exempt(request.path) and not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        return self.get_response(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        """Return True if the given path does not require authentication."""
        return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)
