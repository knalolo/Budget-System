"""Business logic services for the deliveries app (DeliverySubmission workflows)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.services.file_service import save_attachment

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.core.files.uploadedfile import UploadedFile

from .models import DeliverySubmission

logger = logging.getLogger(__name__)


def create_delivery_submission(
    data: dict,
    user: "AbstractUser",
    files: list["UploadedFile"] | None = None,
) -> DeliverySubmission:
    """
    Create a DeliverySubmission and persist any attached files.

    The submission is immediately set to status='submitted'.
    Email notification will be wired in a later phase.

    Args:
        data:  Dict of field values (vendor, currency, total_price,
               purchase_request – optional).
        user:  The authenticated user submitting the record.
        files: Optional list of uploaded files to attach.

    Returns:
        The saved DeliverySubmission instance.
    """
    submission = DeliverySubmission(
        requester=user,
        vendor=data["vendor"],
        currency=data["currency"],
        total_price=data["total_price"],
        purchase_request=data.get("purchase_request"),
        status="submitted",
    )
    submission.save()

    if files:
        for uploaded_file in files:
            try:
                save_attachment(
                    uploaded_file=uploaded_file,
                    content_object=submission,
                    file_type="delivery_order",
                    uploaded_by=user,
                )
            except Exception:
                logger.exception(
                    "Failed to save attachment '%s' for DeliverySubmission #%s.",
                    getattr(uploaded_file, "name", "unknown"),
                    submission.pk,
                )

    logger.info(
        "DeliverySubmission #%s created by user #%s (vendor=%s).",
        submission.pk,
        user.pk,
        submission.vendor,
    )
    return submission
