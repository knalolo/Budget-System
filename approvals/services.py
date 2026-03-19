"""
Generic two-level approval service.

Works with any Django model ("approvable") that exposes the
following fields:

    status                CharField
    requester             FK -> User

    pcm_approver          FK -> User (nullable)
    pcm_decision          CharField  ('pending' | 'approved' | 'rejected')
    pcm_comment           TextField
    pcm_decided_at        DateTimeField (nullable)

    final_approver        FK -> User (nullable)
    final_decision        CharField  ('pending' | 'approved' | 'rejected')
    final_comment         TextField
    final_decided_at      DateTimeField (nullable)

The service never mutates the caller's object in unexpected ways:
it modifies only the well-known approval fields, calls save(), and
returns the updated instance.
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

    The level (PCM vs final) is inferred automatically from the
    object's current status.

    *decision* must be 'approved' or 'rejected'.

    Raises ValidationError for:
    - Invalid status (object not awaiting any approval)
    - Invalid decision value
    - Approver is the requester
    Returns the saved instance.
    """
    if decision not in (DECISION_APPROVED, DECISION_REJECTED):
        raise ValidationError(
            f"Invalid decision '{decision}'. Must be 'approved' or 'rejected'."
        )

    current_status = request_obj.status
    now = timezone.now()

    if current_status == STATUS_PENDING_PCM:
        return _process_pcm_level(
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


def _process_pcm_level(request_obj, approver, decision, comment, now, old_status):
    """Handle PCM-level approval or rejection."""
    _validate_not_self_approval(request_obj, approver)

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
        "PCM %s %s #%s (decision=%s).",
        approver.pk,
        type(request_obj).__name__,
        request_obj.pk,
        decision,
    )

    _fire_notification(request_obj, action, old_status, new_status)

    return request_obj


def _process_final_level(request_obj, approver, decision, comment, now, old_status):
    """Handle final-level approval or rejection."""
    _validate_not_self_approval(request_obj, approver)

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


def _validate_not_self_approval(request_obj, approver) -> None:
    """Raise ValidationError if the approver is also the requester."""
    if request_obj.requester_id == approver.pk:
        raise ValidationError(
            "Requesters cannot approve their own submissions."
        )


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

    # Requesters cannot approve their own submissions
    if getattr(request_obj, "requester_id", None) == user.pk:
        return False, "Requesters cannot approve their own submissions."

    # Role-based check via UserProfile (if available)
    user_role = _get_user_role(user)

    if current_status == STATUS_PENDING_PCM:
        if user_role not in ("pcm_approver", "admin"):
            return False, (
                "Only PCM Approvers can review items at the PCM stage."
            )
        return True, "User may approve at PCM level."

    # STATUS_PENDING_FINAL
    if user_role not in ("final_approver", "admin"):
        return False, (
            "Only Final Approvers can review items at the final stage."
        )
    return True, "User may approve at final level."


def _get_user_role(user) -> str:
    """
    Return the role string for *user* from UserProfile, defaulting to
    'requester' if no profile exists or the role is unset.
    """
    try:
        return user.profile.role  # type: ignore[attr-defined]
    except AttributeError:
        return "requester"
