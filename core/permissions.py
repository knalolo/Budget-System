"""
DRF permission classes for the procurement approval system.

Role hierarchy (lowest -> highest):
    requester < pcm_approver < final_approver < admin

All classes handle the case where UserProfile does not exist yet (other apps
may not be migrated) by defaulting to deny access.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from django.conf import settings

# Role constants pulled from settings to stay DRY
_ROLE_REQUESTER = getattr(settings, "ROLE_REQUESTER", "requester")
_ROLE_PCM_APPROVER = getattr(settings, "ROLE_PCM_APPROVER", "pcm_approver")
_ROLE_FINAL_APPROVER = getattr(settings, "ROLE_FINAL_APPROVER", "final_approver")
_ROLE_ADMIN = getattr(settings, "ROLE_ADMIN", "admin")

# Ordered from least to most privileged so that "or higher" checks are easy.
_ROLE_RANK: dict[str, int] = {
    _ROLE_REQUESTER: 1,
    _ROLE_PCM_APPROVER: 2,
    _ROLE_FINAL_APPROVER: 3,
    _ROLE_ADMIN: 4,
}

_APPROVER_ROLES = {_ROLE_PCM_APPROVER, _ROLE_FINAL_APPROVER, _ROLE_ADMIN}


def _get_role(user) -> str | None:
    """Return the user's role string, or None if the profile is absent."""
    try:
        return user.userprofile.role
    except AttributeError:
        return None


def _has_min_role(user, min_role: str) -> bool:
    """Return True if the user's role rank is >= *min_role*'s rank."""
    role = _get_role(user)
    if role is None:
        return False
    user_rank = _ROLE_RANK.get(role, 0)
    required_rank = _ROLE_RANK.get(min_role, 999)
    return user_rank >= required_rank


# ---------------------------------------------------------------------------
# Permission classes
# ---------------------------------------------------------------------------

class IsRequester(BasePermission):
    """
    Allow any authenticated user with role 'requester' or higher.

    In practice this allows all roles since requester is the lowest rank.
    """

    message = "You must have at least the Requester role."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return _has_min_role(request.user, _ROLE_REQUESTER)


class IsPCMApprover(BasePermission):
    """Allow users with exactly the 'pcm_approver' role."""

    message = "You must have the PCM Approver role."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return _get_role(request.user) == _ROLE_PCM_APPROVER


class IsFinalApprover(BasePermission):
    """Allow users with exactly the 'final_approver' role."""

    message = "You must have the Final Approver role."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return _get_role(request.user) == _ROLE_FINAL_APPROVER


class IsAdmin(BasePermission):
    """Allow users with the 'admin' role."""

    message = "You must have the Admin role."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return _get_role(request.user) == _ROLE_ADMIN


class IsOwnerOrApprover(BasePermission):
    """
    Allow access if the user is the owner of the object, OR has any
    approver-level role (pcm_approver, final_approver, admin).

    Object-level check: the related object is expected to expose a
    ``requester`` attribute pointing to the owning User. Falls back to
    checking for a ``user`` attribute if ``requester`` is absent.
    """

    message = "You must be the owner of this record or have an approver role."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        # Approvers can always access any object.
        role = _get_role(request.user)
        if role in _APPROVER_ROLES:
            return True

        # Check ownership – try common attribute names.
        owner = getattr(obj, "requester", None) or getattr(obj, "user", None)
        if owner is not None:
            return owner == request.user

        return False
