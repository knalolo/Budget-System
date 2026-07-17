"""Business logic services for the orders app (PurchaseRequest workflows)."""
from __future__ import annotations

import logging

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

import approvals.services as approval_service
from approvals.models import ACTION_STATUS_CHANGED, ApprovalLog
from core.models import SystemConfig
from core.services.email_service import notify_submission

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PO threshold keys in SystemConfig
# ---------------------------------------------------------------------------

_PO_THRESHOLD_KEYS: dict[str, str] = {
    "SGD": "po_threshold_sgd",
    "USD": "po_threshold_usd",
    "EUR": "po_threshold_eur",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def check_po_threshold(currency: str, total_price) -> bool:
    """
    Return True when *total_price* meets or exceeds the configured PO
    threshold for *currency*.

    Returns False when no threshold is configured for the given currency
    or the stored value is non-numeric.
    """
    config_key = _PO_THRESHOLD_KEYS.get(currency.upper())
    if config_key is None:
        return False

    threshold = SystemConfig.get_value(config_key)
    if threshold is None:
        return False

    try:
        return total_price >= threshold
    except TypeError:
        logger.warning(
            "PO threshold for currency %s (%r) is non-numeric; treating as not required.",
            currency,
            threshold,
        )
        return False


# ---------------------------------------------------------------------------
# Purchase request lifecycle services
# ---------------------------------------------------------------------------


def submit_purchase_request(purchase_request):
    """
    Validate and submit *purchase_request* for approval.

    Validation:
    - Status must be 'draft' or 'rejected'.
    - Must have at least one attachment (logged as a warning; does not block
      submission when relaxed mode is intended but logs clearly).

    Side effects:
    - Updates po_required based on current PO thresholds.
    - Delegates to approvals.services.submit_for_approval() to transition
      status to first-stage approval and record the submission log.

    Returns the updated instance.
    Raises ValidationError on hard failures.
    """
    if purchase_request.status not in ("draft", "rejected"):
        raise ValidationError(
            f"Only draft or rejected purchase requests can be submitted. "
            f"Current status: '{purchase_request.status}'."
        )

    attachment_count = purchase_request.attachments.count()
    if attachment_count == 0:
        logger.warning(
            "PurchaseRequest #%s submitted without attachments.",
            purchase_request.pk,
        )

    # Auto-update po_required from current thresholds
    computed_po = check_po_threshold(purchase_request.currency, purchase_request.total_price)
    if purchase_request.po_required != computed_po:
        purchase_request.po_required = computed_po
        purchase_request.save(update_fields=["po_required"])

    purchase_request = approval_service.submit_for_approval(purchase_request)

    logger.info(
        "PurchaseRequest #%s submitted for approval (po_required=%s).",
        purchase_request.pk,
        purchase_request.po_required,
    )

    try:
        notify_submission(purchase_request, "purchase_request")
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to send submission notification for PurchaseRequest #%s: %s",
            purchase_request.pk,
            exc,
        )

    return purchase_request


def approve_purchase_request(purchase_request, approver, comment: str = ""):
    """
    Record an approval decision by *approver* at the current approval level.

    Delegates entirely to approvals.services.process_approval().
    Returns the updated instance.
    """
    purchase_request = approval_service.process_approval(
        purchase_request, approver, "approved", comment
    )
    logger.info(
        "PurchaseRequest #%s approved by user #%s.",
        purchase_request.pk,
        approver.pk,
    )
    return purchase_request


def reject_purchase_request(purchase_request, approver, comment: str = ""):
    """
    Record a rejection decision by *approver* at the current approval level.

    Delegates entirely to approvals.services.process_approval().
    Returns the updated instance.
    """
    purchase_request = approval_service.process_approval(
        purchase_request, approver, "rejected", comment
    )
    logger.info(
        "PurchaseRequest #%s rejected by user #%s.",
        purchase_request.pk,
        approver.pk,
    )
    return purchase_request


def request_purchase_request_cancellation(purchase_request, requester, reason: str):
    """Request final-approver cancellation for an approved purchase request."""
    if purchase_request.requester_id != requester.pk:
        raise ValidationError("Only the requester can request cancellation.")
    if purchase_request.status != "approved":
        raise ValidationError("Only approved purchase requests can request cancellation.")
    if purchase_request.workflow_completed:
        raise ValidationError("Completed workflows cannot request cancellation.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Cancellation reason is required.")

    old_status = purchase_request.status
    purchase_request.status = "cancellation_pending"
    purchase_request.cancellation_requested_by = requester
    purchase_request.cancellation_requested_at = timezone.now()
    purchase_request.cancellation_reason = reason
    purchase_request.cancellation_decision = "pending"
    purchase_request.cancellation_decided_by = None
    purchase_request.cancellation_decided_at = None
    purchase_request.cancellation_decision_comment = ""
    purchase_request.save(
        update_fields=[
            "status",
            "cancellation_requested_by",
            "cancellation_requested_at",
            "cancellation_reason",
            "cancellation_decision",
            "cancellation_decided_by",
            "cancellation_decided_at",
            "cancellation_decision_comment",
            "updated_at",
        ]
    )
    _create_status_log(
        purchase_request,
        old_status,
        purchase_request.status,
        actor=requester,
        comment=reason,
    )
    return purchase_request


def approve_purchase_request_cancellation(purchase_request, approver, comment: str = ""):
    """Approve a pending cancellation request and mark the PR cancelled."""
    _validate_cancellation_decider(purchase_request, approver)
    old_status = purchase_request.status
    purchase_request.status = "cancelled"
    purchase_request.cancellation_decision = "approved"
    purchase_request.cancellation_decided_by = approver
    purchase_request.cancellation_decided_at = timezone.now()
    purchase_request.cancellation_decision_comment = (comment or "").strip()
    purchase_request.save(
        update_fields=[
            "status",
            "cancellation_decision",
            "cancellation_decided_by",
            "cancellation_decided_at",
            "cancellation_decision_comment",
            "updated_at",
        ]
    )
    _create_status_log(
        purchase_request,
        old_status,
        purchase_request.status,
        actor=approver,
        comment=comment,
    )
    return purchase_request


def reject_purchase_request_cancellation(purchase_request, approver, comment: str = ""):
    """Reject a pending cancellation request and return the PR to approved."""
    _validate_cancellation_decider(purchase_request, approver)
    old_status = purchase_request.status
    purchase_request.status = "approved"
    purchase_request.cancellation_decision = "rejected"
    purchase_request.cancellation_decided_by = approver
    purchase_request.cancellation_decided_at = timezone.now()
    purchase_request.cancellation_decision_comment = (comment or "").strip()
    purchase_request.save(
        update_fields=[
            "status",
            "cancellation_decision",
            "cancellation_decided_by",
            "cancellation_decided_at",
            "cancellation_decision_comment",
            "updated_at",
        ]
    )
    _create_status_log(
        purchase_request,
        old_status,
        purchase_request.status,
        actor=approver,
        comment=comment,
    )
    return purchase_request


def mark_po_sent(purchase_request):
    """
    Compatibility helper retained for historical callers.

    The retired ``po_sent`` execution stage is no longer part of the active
    procurement workflow. This helper now leaves the purchase request
    unchanged and simply returns the current instance.
    """
    logger.info(
        "mark_po_sent called for PurchaseRequest #%s, but the PO Sent stage is retired.",
        purchase_request.pk,
    )
    return purchase_request


def mark_ordered(purchase_request):
    """
    Compatibility helper retained for historical callers.

    The retired ``ordered`` execution stage is no longer part of the active
    procurement workflow. This helper now leaves the purchase request
    unchanged and simply returns the current instance.
    """
    logger.info(
        "mark_ordered called for PurchaseRequest #%s, but the Ordered stage is retired.",
        purchase_request.pk,
    )
    return purchase_request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_cancellation_decider(purchase_request, approver) -> None:
    if purchase_request.status != "cancellation_pending":
        raise ValidationError("Only pending cancellation requests can be decided.")
    profile = getattr(approver, "profile", None)
    if not (profile and (profile.is_final_approver or profile.is_admin)):
        raise ValidationError("Only Final Approver or Admin can decide cancellation requests.")


def _create_status_log(
    obj,
    old_status: str,
    new_status: str,
    *,
    actor=None,
    comment: str = "",
) -> ApprovalLog:
    """Create an ApprovalLog entry for a manual status change on *obj*."""
    content_type = ContentType.objects.get_for_model(obj)
    return ApprovalLog.objects.create(
        content_type=content_type,
        object_id=obj.pk,
        action=ACTION_STATUS_CHANGED,
        action_by=actor or obj.requester,
        old_status=old_status,
        new_status=new_status,
        comment=comment or "",
    )
