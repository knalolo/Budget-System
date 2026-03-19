"""Business logic services for the payments app (PaymentRelease workflows)."""
from __future__ import annotations

import logging

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
