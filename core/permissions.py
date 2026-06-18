"""
DRF permission classes for the procurement approval system.

The application now uses a multi-permission user profile instead of a
single role string. These helpers intentionally read the new boolean
flags first and only fall back to deny when no profile exists.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


def _get_profile(user):
    """Return the user's profile or None if it is missing."""
    try:
        return user.profile
    except AttributeError:
        return None


def _is_authenticated(user) -> bool:
    """Small helper to keep permission checks tidy."""
    return bool(user and user.is_authenticated)


def _is_first_stage_approver(profile) -> bool:
    """Return True when the profile can approve any Purchase Type first stage."""
    return bool(
        profile
        and (
            profile.is_project_approver
            or profile.is_non_project_approver
            or profile.is_office_approver
            or profile.is_pcm_approver
        )
    )


class IsRequester(BasePermission):
    """Allow authenticated users who can create requests."""

    message = "You must have requester permission."

    def has_permission(self, request, view) -> bool:
        if not _is_authenticated(request.user):
            return False
        profile = _get_profile(request.user)
        return bool(profile and (profile.is_requester or profile.is_admin))


class IsPurchaseTypeApprover(BasePermission):
    """
    Allow users with any first-stage Purchase Type approver permission.

    Legacy API endpoints still refer to PCM approval. Internally we keep a
    compatibility alias below so older imports continue to work.
    """

    message = "You must have Purchase Type approver permission."

    def has_permission(self, request, view) -> bool:
        if not _is_authenticated(request.user):
            return False
        profile = _get_profile(request.user)
        return bool(
            (profile and _is_first_stage_approver(profile))
            or (profile and profile.is_admin)
        )


class IsPCMApprover(IsPurchaseTypeApprover):
    """Backward-compatible alias for legacy PCM-named API code paths."""


class IsFinalApprover(BasePermission):
    """Allow users with final-approver permission or admin access."""

    message = "You must have final approver permission."

    def has_permission(self, request, view) -> bool:
        if not _is_authenticated(request.user):
            return False
        profile = _get_profile(request.user)
        return bool(profile and (profile.is_final_approver or profile.is_admin))


class IsAdmin(BasePermission):
    """Allow users with standalone admin permission or Django staff."""

    message = "You must have admin permission."

    def has_permission(self, request, view) -> bool:
        if not _is_authenticated(request.user):
            return False
        if request.user.is_staff:
            return True
        profile = _get_profile(request.user)
        return bool(profile and profile.is_admin)


class IsOwnerOrApprover(BasePermission):
    """
    Allow access if the user owns the object or has approver/admin rights.

    Object-level check: the related object is expected to expose either a
    ``requester`` or ``user`` attribute.
    """

    message = "You must be the owner of this record or have approval access."

    def has_permission(self, request, view) -> bool:
        return _is_authenticated(request.user)

    def has_object_permission(self, request, view, obj) -> bool:
        if not _is_authenticated(request.user):
            return False

        profile = _get_profile(request.user)
        if profile and (
            profile.is_admin
            or _is_first_stage_approver(profile)
            or profile.is_final_approver
        ):
            return True

        owner = getattr(obj, "requester", None) or getattr(obj, "user", None)
        return owner == request.user if owner is not None else False
