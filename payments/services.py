"""Business logic services for the payments app (PaymentRelease workflows)."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError

import approvals.services as approval_service

logger = logging.getLogger(__name__)


def submit_payment_release(payment_release):
    """
    Validate and submit *payment_release* for approval.

    Validation:
    - Status must be 'draft'.
    - Logs a warning if no attachments are present.

    Delegates to approvals.services.submit_for_approval() to transition
    status to 'pending_pcm' and record the submission log.

    Returns the updated instance.
    Raises ValidationError on hard failures.
    """
    if payment_release.status != "draft":
        raise ValidationError(
            f"Only draft payment releases can be submitted. "
            f"Current status: '{payment_release.status}'."
        )

    attachment_count = payment_release.attachments.count()
    if attachment_count == 0:
        logger.warning(
            "PaymentRelease #%s submitted without attachments.",
            payment_release.pk,
        )

    _validate_delivery_and_payment_limits(payment_release)

    payment_release = approval_service.submit_for_approval(payment_release)

    logger.info(
        "PaymentRelease #%s submitted for approval.",
        payment_release.pk,
    )

    return payment_release


def approve_payment_release(payment_release, approver, comment: str = ""):
    """
    Record an approval decision by *approver* at the current approval level.

    Delegates entirely to approvals.services.process_approval().
    Returns the updated instance.
    """
    payment_release = approval_service.process_approval(
        payment_release, approver, "approved", comment
    )
    logger.info(
        "PaymentRelease #%s approved by user #%s.",
        payment_release.pk,
        approver.pk,
    )
    return payment_release


def reject_payment_release(payment_release, approver, comment: str = ""):
    """
    Record a rejection decision by *approver* at the current approval level.

    Delegates entirely to approvals.services.process_approval().
    Returns the updated instance.
    """
    payment_release = approval_service.process_approval(
        payment_release, approver, "rejected", comment
    )
    logger.info(
        "PaymentRelease #%s rejected by user #%s.",
        payment_release.pk,
        approver.pk,
    )
    return payment_release


def _validate_delivery_and_payment_limits(payment_release) -> None:
    """Enforce delivery-first payment rules unless the request is an advance payment."""
    purchase_request = payment_release.purchase_request
    if purchase_request is None:
        return

    if payment_release.payment_quantity > purchase_request.ordered_quantity:
        raise ValidationError(
            "Payment quantity cannot exceed the ordered quantity on the purchase request."
        )

    if payment_release.payment_type == "advance":
        return

    if purchase_request.delivered_quantity <= 0:
        raise ValidationError(
            "Standard payments require a goods recieve record first. Use Advance Payment only when the supplier requires prepayment."
        )

    available_quantity = purchase_request.available_standard_payment_quantity
    if available_quantity <= 0:
        raise ValidationError(
            "There is no goods recieve quantity left to pay against this purchase request."
        )

    remaining_payable_total = purchase_request.remaining_payable_total
    if remaining_payable_total <= Decimal("0.00"):
        raise ValidationError(
            "This purchase request has already been fully covered by existing payment releases."
        )

    if payment_release.payment_quantity > available_quantity:
        raise ValidationError(
            f"Only {available_quantity} delivered unit(s) are currently available for standard payment."
        )

    unit_price = purchase_request.unit_price
    max_total = min(
        unit_price * Decimal(payment_release.payment_quantity),
        remaining_payable_total,
    )
    if payment_release.total_price > max_total:
        raise ValidationError(
            f"Standard payment cannot exceed {purchase_request.currency} {max_total:.2f} for {payment_release.payment_quantity} delivered unit(s)."
        )
