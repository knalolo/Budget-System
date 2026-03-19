"""
MSAL (Microsoft Authentication Library) integration service for Azure AD SSO.

Provides:
  - get_msal_app()          – Build a ConfidentialClientApplication instance.
  - get_auth_url(request)   – Generate the Azure AD authorization URL.
  - process_auth_callback() – Exchange the auth code, fetch Graph user info,
                              and create/update the Django User + UserProfile.
  - get_user_from_graph()   – Call Microsoft Graph /me endpoint.
"""
import logging
import secrets
import urllib.parse
from typing import Any

import msal
import requests
from django.conf import settings
from django.contrib.auth.models import User

from accounts.models import UserProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_ME_ENDPOINT = "https://graph.microsoft.com/v1.0/me"
_SESSION_STATE_KEY = "msal_auth_state"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_msal_app() -> msal.ConfidentialClientApplication:
    """
    Build and return an MSAL ConfidentialClientApplication.

    Raises ValueError if the required Azure AD settings are not configured.
    """
    tenant_id = settings.AZURE_AD_TENANT_ID
    client_id = settings.AZURE_AD_CLIENT_ID
    client_secret = settings.AZURE_AD_CLIENT_SECRET

    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            "Azure AD is not fully configured. "
            "Set AZURE_AD_TENANT_ID, AZURE_AD_CLIENT_ID, and AZURE_AD_CLIENT_SECRET."
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def get_auth_url(request: Any) -> str:
    """
    Generate the Azure AD authorization URL and store the CSRF state in the session.

    Args:
        request: Django HttpRequest (needs session support).

    Returns:
        The full Azure AD authorization URL the browser should be redirected to.

    Raises:
        ValueError: If Azure AD settings are not configured.
    """
    app = get_msal_app()

    # Generate a cryptographically secure random state value for CSRF protection.
    state = secrets.token_urlsafe(32)
    request.session[_SESSION_STATE_KEY] = state

    auth_url = app.get_authorization_request_url(
        scopes=settings.AZURE_AD_SCOPES,
        state=state,
        redirect_uri=settings.AZURE_AD_REDIRECT_URI,
    )

    return auth_url


def get_user_from_graph(access_token: str) -> dict:
    """
    Call the Microsoft Graph /me endpoint with the given access token.

    Args:
        access_token: A valid OAuth2 access token for the user.

    Returns:
        A dict containing the user's Graph profile information.

    Raises:
        RuntimeError: If the Graph API call fails.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(GRAPH_ME_ENDPOINT, headers=headers, timeout=10)

    if not response.ok:
        logger.error(
            "Microsoft Graph /me request failed: %s %s",
            response.status_code,
            response.text,
        )
        raise RuntimeError(
            f"Failed to fetch user info from Microsoft Graph (HTTP {response.status_code})."
        )

    return response.json()


def process_auth_callback(request: Any) -> User:
    """
    Handle the Azure AD OAuth2 callback.

    Steps:
      1. Validate the state parameter against the session value (CSRF check).
      2. Exchange the authorization code for tokens via MSAL.
      3. Call Microsoft Graph to retrieve the user's profile.
      4. Create or update the Django User and UserProfile.
      5. Return the Django User object ready for django.contrib.auth.login().

    Args:
        request: Django HttpRequest containing GET params (code, state) and session.

    Returns:
        The authenticated Django User instance.

    Raises:
        ValueError: On state mismatch, missing code, or MSAL token error.
        RuntimeError: On Graph API failure.
    """
    # --- CSRF state validation ---
    expected_state = request.session.get(_SESSION_STATE_KEY)
    received_state = request.GET.get("state")

    if not expected_state or expected_state != received_state:
        logger.warning(
            "MSAL state mismatch: expected=%r received=%r",
            expected_state,
            received_state,
        )
        raise ValueError("Invalid state parameter – possible CSRF attack.")

    # Clean up state from session immediately after validation.
    request.session.pop(_SESSION_STATE_KEY, None)

    # --- Authorization code exchange ---
    auth_code = request.GET.get("code")
    if not auth_code:
        error = request.GET.get("error", "unknown_error")
        error_description = request.GET.get("error_description", "No authorization code returned.")
        logger.error("Azure AD callback error: %s – %s", error, error_description)
        raise ValueError(f"Authorization failed: {error_description}")

    app = get_msal_app()
    token_result = app.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=settings.AZURE_AD_SCOPES,
        redirect_uri=settings.AZURE_AD_REDIRECT_URI,
    )

    if "error" in token_result:
        logger.error(
            "MSAL token acquisition failed: %s – %s",
            token_result.get("error"),
            token_result.get("error_description"),
        )
        raise ValueError(
            f"Token acquisition failed: {token_result.get('error_description', token_result.get('error'))}"
        )

    access_token = token_result.get("access_token", "")
    id_token_claims = token_result.get("id_token_claims", {})

    # --- Fetch user profile from Graph ---
    graph_user = get_user_from_graph(access_token)

    # --- Build user field values (immutable derivation) ---
    azure_oid = id_token_claims.get("oid", graph_user.get("id", ""))
    email = graph_user.get("mail") or graph_user.get("userPrincipalName", "")
    display_name = graph_user.get("displayName", "")
    given_name = graph_user.get("givenName", "")
    surname = graph_user.get("surname", "")

    # Derive a username from the email prefix (before @).
    username = email.split("@")[0] if "@" in email else email

    # --- Create or update Django User ---
    user = _upsert_user(
        azure_oid=azure_oid,
        username=username,
        email=email,
        first_name=given_name,
        last_name=surname,
        display_name=display_name,
    )

    return user


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _upsert_user(
    *,
    azure_oid: str,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    display_name: str,
) -> User:
    """
    Find an existing user by azure_oid (or email as fallback) and update their
    information, or create a new user if none is found.

    Returns the saved Django User instance.
    """
    user: User | None = None

    # Primary lookup: by azure_oid on the UserProfile.
    if azure_oid:
        try:
            profile = UserProfile.objects.select_related("user").get(azure_oid=azure_oid)
            user = profile.user
        except UserProfile.DoesNotExist:
            pass

    # Fallback: match by email address.
    if user is None and email:
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            pass

    if user is None:
        # Create a new inactive-password user (SSO only).
        user = User.objects.create_user(
            username=_unique_username(username),
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save()
        logger.info("Created new SSO user: %s (%s)", user.username, email)
    else:
        # Update mutable fields on existing user (immutable pattern: save new values).
        User.objects.filter(pk=user.pk).update(
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        # Refresh from DB to get updated state.
        user.refresh_from_db()
        logger.info("Updated existing SSO user: %s (%s)", user.username, email)

    # Ensure UserProfile exists and is up-to-date.
    profile, _ = UserProfile.objects.get_or_create(user=user)
    UserProfile.objects.filter(pk=profile.pk).update(
        azure_oid=azure_oid or None,
        display_name=display_name,
    )

    # Attach the backend so django.contrib.auth.login() works without a password check.
    user.backend = "django.contrib.auth.backends.ModelBackend"

    return user


def _unique_username(base: str) -> str:
    """
    Return a username that does not already exist in the database.

    If ``base`` is taken, appends an incrementing integer suffix.
    """
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username
