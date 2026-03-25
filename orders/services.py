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
    - Status must be 'draft'.
    - Must have at least one attachment (logged as a warning; does not block
      submission when relaxed mode is intended but logs clearly).

    Side effects:
    - Updates po_required based on current PO thresholds.
    - Delegates to approvals.services.submit_for_approval() to transition
      status to 'pending_pcm' and record the submission log.

    Returns the updated instance.
    Raises ValidationError on hard failures.
    """
    if purchase_request.status != "draft":
        raise ValidationError(
            f"Only draft purchase requests can be submitted. "
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


def mark_po_sent(purchase_request):
    """
    Transition an approved purchase request to 'po_sent'.

    Validation: status must be 'approved'.
    Creates an ApprovalLog entry with ACTION_STATUS_CHANGED.
    Returns the updated instance.
    Raises ValidationError if precondition is not met.
    """
    if purchase_request.status != "approved":
        raise ValidationError(
            f"Only approved purchase requests can be marked as PO sent. "
            f"Current status: '{purchase_request.status}'."
        )

    old_status = purchase_request.status
    purchase_request.status = "po_sent"
    purchase_request.save(update_fields=["status", "updated_at"])

    _create_status_log(purchase_request, old_status, "po_sent")

    logger.info("PurchaseRequest #%s marked as po_sent.", purchase_request.pk)
    return purchase_request


def mark_ordered(purchase_request):
    """
    Transition a purchase request to 'ordered'.

    Validation:
    - PO-required requests must first be marked as 'po_sent'.
    - Non-PO requests may transition from 'approved' or 'po_sent'.
    Creates an ApprovalLog entry with ACTION_STATUS_CHANGED.
    Returns the updated instance.
    Raises ValidationError if precondition is not met.
    """
    if purchase_request.po_required:
        allowed_statuses = ("po_sent",)
        error_message = (
            "PO-required purchase requests must be marked as PO sent before they can be marked as ordered. "
            f"Current status: '{purchase_request.status}'."
        )
    else:
        allowed_statuses = ("approved", "po_sent")
        error_message = (
            "Purchase request must be 'approved' or 'po_sent' to be marked as ordered. "
            f"Current status: '{purchase_request.status}'."
        )

    if purchase_request.status not in allowed_statuses:
        raise ValidationError(
            error_message
        )

    old_status = purchase_request.status
    purchase_request.status = "ordered"
    purchase_request.save(update_fields=["status", "updated_at"])

    _create_status_log(purchase_request, old_status, "ordered")

    logger.info("PurchaseRequest #%s marked as ordered.", purchase_request.pk)
    return purchase_request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_status_log(obj, old_status: str, new_status: str) -> ApprovalLog:
    """Create an ApprovalLog entry for a manual status change on *obj*."""
    content_type = ContentType.objects.get_for_model(obj)
    return ApprovalLog.objects.create(
        content_type=content_type,
        object_id=obj.pk,
        action=ACTION_STATUS_CHANGED,
        action_by=obj.requester,
        old_status=old_status,
        new_status=new_status,
        comment="",
    )
