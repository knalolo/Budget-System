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
    - Status must be 'draft' or 'rejected'.
    - Logs a warning if no attachments are present.

    Delegates to approvals.services.submit_for_approval() to transition
    status to first-stage approval and record the submission log.

    Returns the updated instance.
    Raises ValidationError on hard failures.
    """
    if payment_release.status not in ("draft", "rejected"):
        raise ValidationError(
            f"Only draft or rejected payment releases can be submitted. "
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

    other_pending_payment = purchase_request.payment_releases.filter(
        status__in=("pending_pcm", "pending_final")
    ).exclude(pk=payment_release.pk).first()
    if other_pending_payment is not None:
        raise ValidationError(
            f"Payment release {other_pending_payment.request_number} is still under approval. "
            "Complete or reject it before submitting another payment."
        )

    if purchase_request.is_delivery_first and payment_release.payment_type == "advance":
        raise ValidationError(
            "This purchase request is goods receive first. Submit goods receive before creating the payment release."
        )

    if (
        purchase_request.is_payment_first
        and purchase_request.delivered_quantity <= 0
        and payment_release.payment_type != "advance"
    ):
        raise ValidationError(
            "This purchase request is payment first. Submit an advance payment release before goods receive."
        )

    if payment_release.payment_quantity > purchase_request.ordered_quantity:
        raise ValidationError(
            "Payment quantity cannot exceed the ordered quantity on the purchase request."
        )

    remaining_payable_total = purchase_request.remaining_payable_total
    if remaining_payable_total <= Decimal("0.00"):
        raise ValidationError(
            "This purchase request has already been fully covered by existing payment releases."
        )

    if payment_release.total_price > remaining_payable_total:
        raise ValidationError(
            f"This payment cannot exceed the remaining payable amount of "
            f"{purchase_request.currency} {remaining_payable_total:.2f}."
        )

    if payment_release.payment_type == "advance":
        return

    if purchase_request.delivered_quantity <= 0:
        raise ValidationError(
            "Standard payments require a goods recieve record first. "
            "Use Advance Payment only when the supplier requires prepayment."
        )

    available_quantity = purchase_request.available_standard_payment_quantity
    if available_quantity <= 0:
        raise ValidationError(
            "There is no goods recieve quantity left to pay against this purchase request."
        )

    if payment_release.payment_quantity > available_quantity:
        raise ValidationError(
            f"Only {available_quantity} delivered unit(s) are currently available for standard payment."
        )

    max_total = purchase_request.max_standard_payment_total
    if payment_release.total_price > max_total:
        raise ValidationError(
            f"Standard payment cannot exceed {purchase_request.currency} {max_total:.2f} "
            "based on the delivered goods currently available."
        )
