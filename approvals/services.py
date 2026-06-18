"""
Generic two-level approval service.

The first approval stage is routed by purchase type:

    project      -> Project Approver
    non_project  -> Non-Project Approver
    office       -> Office Approver

The final approval stage is always handled by the Final Approver.

Legacy database field names such as ``pcm_approver`` are retained for
backward compatibility while the UI and data model are being migrated.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    ACTION_FINAL_APPROVED,
    ACTION_FINAL_REJECTED,
    ACTION_PCM_APPROVED,
    ACTION_PCM_REJECTED,
    ACTION_SUBMITTED,
    ApprovalLog,
)

# Email notifications are imported lazily inside functions to avoid circular
# imports between the approvals and core apps.

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

User = get_user_model()

# ---------------------------------------------------------------------------
# Status constants (mirrors config/settings/base.py values)
# ---------------------------------------------------------------------------

STATUS_DRAFT = "draft"
STATUS_PENDING_PCM = "pending_pcm"
STATUS_PENDING_FINAL = "pending_final"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_stage_flag_name(request_obj) -> str:
    purchase_type = getattr(request_obj, "purchase_type", "")
    flag_map = {
        "project": "is_project_approver",
        "non_project": "is_non_project_approver",
        "office": "is_office_approver",
    }
    return flag_map.get(purchase_type, "")


def _has_active_profile_flag(flag_name: str) -> bool:
    if not flag_name:
        return False
    return User.objects.filter(
        is_active=True,
        **{f"profile__{flag_name}": True},
    ).exists()


def _validate_assigned_approver_chain(request_obj) -> None:
    first_stage_flag = _first_stage_flag_name(request_obj)
    first_stage_label = getattr(
        request_obj,
        "first_approver_role_label",
        "Approver",
    )

    if not _has_active_profile_flag(first_stage_flag):
        raise ValidationError(
            f"Cannot submit this request because no active {first_stage_label} is assigned."
        )

    if not _has_active_profile_flag("is_final_approver"):
        raise ValidationError(
            "Cannot submit this request because no active Final Approver is assigned."
        )


def _create_log(
    obj,
    action: str,
    actor,
    old_status: str,
    new_status: str,
    comment: str = "",
) -> ApprovalLog:
    """Create and return an ApprovalLog entry for *obj*."""
    content_type = ContentType.objects.get_for_model(obj)
    return ApprovalLog.objects.create(
        content_type=content_type,
        object_id=obj.pk,
        action=action,
        action_by=actor,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def submit_for_approval(request_obj):
    """
    Transition *request_obj* from 'draft' to 'pending_pcm'.

    Raises ValidationError if the object is not in draft status.
    Returns the saved instance.
    """
    current_status = request_obj.status

    if current_status != STATUS_DRAFT:
        raise ValidationError(
            f"Only draft items can be submitted for approval. "
            f"Current status: '{current_status}'."
        )

    _validate_assigned_approver_chain(request_obj)

    requester = request_obj.requester
    request_obj.status = STATUS_PENDING_PCM
    request_obj.save()

    _create_log(
        obj=request_obj,
        action=ACTION_SUBMITTED,
        actor=requester,
        old_status=current_status,
        new_status=STATUS_PENDING_PCM,
    )

    logger.info(
        "Submitted %s #%s for approval by user %s.",
        type(request_obj).__name__,
        request_obj.pk,
        requester.pk,
    )

    return request_obj


def process_approval(request_obj, approver, decision: str, comment: str = ""):
    """
    Process an approval or rejection at the appropriate level.

    The level (Purchase Type approver vs final) is inferred automatically from the
    object's current status.

    *decision* must be 'approved' or 'rejected'.

    Raises ValidationError for:
    - Invalid status (object not awaiting any approval)
    - Invalid decision value
    Returns the saved instance.
    """
    if decision not in (DECISION_APPROVED, DECISION_REJECTED):
        raise ValidationError(
            f"Invalid decision '{decision}'. Must be 'approved' or 'rejected'."
        )

    current_status = request_obj.status
    now = timezone.now()

    if current_status == STATUS_PENDING_PCM:
        return _process_first_stage_level(
            request_obj=request_obj,
            approver=approver,
            decision=decision,
            comment=comment,
            now=now,
            old_status=current_status,
        )

    if current_status == STATUS_PENDING_FINAL:
        return _process_final_level(
            request_obj=request_obj,
            approver=approver,
            decision=decision,
            comment=comment,
            now=now,
            old_status=current_status,
        )

    raise ValidationError(
        f"Cannot process approval: object is in status '{current_status}'. "
        "Expected 'pending_pcm' or 'pending_final'."
    )


def _process_first_stage_level(request_obj, approver, decision, comment, now, old_status):
    """Handle Purchase Type approval or rejection using legacy PCM-backed fields."""
    request_obj.pcm_approver = approver
    request_obj.pcm_decision = decision
    request_obj.pcm_comment = comment
    request_obj.pcm_decided_at = now

    if decision == DECISION_APPROVED:
        new_status = STATUS_PENDING_FINAL
        action = ACTION_PCM_APPROVED
    else:
        new_status = STATUS_REJECTED
        action = ACTION_PCM_REJECTED

    request_obj.status = new_status
    request_obj.save()

    _create_log(
        obj=request_obj,
        action=action,
        actor=approver,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )

    logger.info(
        "Purchase Type approver %s processed %s #%s (decision=%s).",
        approver.pk,
        type(request_obj).__name__,
        request_obj.pk,
        decision,
    )

    _fire_notification(request_obj, action, old_status, new_status)

    return request_obj


def _process_final_level(request_obj, approver, decision, comment, now, old_status):
    """Handle final-level approval or rejection."""
    request_obj.final_approver = approver
    request_obj.final_decision = decision
    request_obj.final_comment = comment
    request_obj.final_decided_at = now

    if decision == DECISION_APPROVED:
        new_status = STATUS_APPROVED
        action = ACTION_FINAL_APPROVED
    else:
        new_status = STATUS_REJECTED
        action = ACTION_FINAL_REJECTED

    request_obj.status = new_status
    request_obj.save()

    _create_log(
        obj=request_obj,
        action=action,
        actor=approver,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )

    logger.info(
        "Final approver %s %s %s #%s (decision=%s).",
        approver.pk,
        type(request_obj).__name__,
        request_obj.pk,
        decision,
    )

    _fire_notification(request_obj, action, old_status, new_status)

    return request_obj


def _fire_notification(
    request_obj,
    action: str,
    old_status: str,
    new_status: str,
) -> None:
    """
    Fire an email notification for the given action without raising exceptions.

    Imported lazily to prevent circular imports between core and approvals.
    """
    try:
        from core.services.email_service import trigger_post_approval_notification
        trigger_post_approval_notification(request_obj, action, old_status, new_status)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "_fire_notification failed for %s #%s action=%r: %s",
            type(request_obj).__name__,
            getattr(request_obj, "pk", "?"),
            action,
            exc,
        )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_approval_history(content_object) -> "QuerySet[ApprovalLog]":
    """
    Return all ApprovalLog entries for *content_object*, newest first.

    Uses the ContentType framework to locate the correct records.
    """
    content_type = ContentType.objects.get_for_model(content_object)
    return ApprovalLog.objects.filter(
        content_type=content_type,
        object_id=content_object.pk,
    )


def can_user_approve(request_obj, user) -> tuple[bool, str]:
    """
    Determine whether *user* is allowed to approve *request_obj*.

    Returns a (bool, reason_string) tuple so callers can surface a
    meaningful error when the check fails.
    """
    current_status = request_obj.status

    if current_status not in (STATUS_PENDING_PCM, STATUS_PENDING_FINAL):
        return False, (
            f"Item is not awaiting approval (status: '{current_status}')."
        )

    profile = _get_user_profile(user)
    if profile is None:
        return False, "User profile not found."

    if current_status == STATUS_PENDING_PCM:
        if not _user_can_handle_first_stage(profile, request_obj):
            return False, (
                f"Only the assigned { _first_approver_role_label(request_obj) } can review this item at the Purchase Type approval stage."
            )
        return True, "User may approve at the Purchase Type approval stage."

    # STATUS_PENDING_FINAL
    if not profile.is_final_approver:
        return False, (
            "Only Final Approvers can review items at the final stage."
        )
    return True, "User may approve at final level."


def _get_user_profile(user):
    """Return the user's profile, or None if it does not exist."""
    try:
        return user.profile  # type: ignore[attr-defined]
    except AttributeError:
        return None


def _user_can_handle_first_stage(profile, request_obj) -> bool:
    """Return True if *profile* may review the request's Purchase Type approval stage."""
    return profile.can_approve_purchase_type(
        getattr(request_obj, "purchase_type", "")
    )


def _first_approver_role_label(request_obj) -> str:
    """Return a human-readable label for the request's first approver stage."""
    return getattr(
        request_obj,
        "first_approver_role_label",
        "Approver",
    )
