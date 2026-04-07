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
    purchase_request = data.get("purchase_request")
    delivered_quantity = data["delivered_quantity"]
    status = data["status"]

    if purchase_request is not None:
        if purchase_request.status in ("approved", "po_sent"):
            from orders.services import mark_ordered

            purchase_request = mark_ordered(purchase_request)

        total_after_delivery = purchase_request.delivered_quantity + delivered_quantity
        remaining_before_delivery = purchase_request.remaining_quantity

        if delivered_quantity > remaining_before_delivery:
            raise ValueError(
                "Delivered quantity cannot exceed the remaining ordered quantity."
            )

        if status == "fully_delivered" and delivered_quantity != remaining_before_delivery:
            raise ValueError(
                "To mark the request as fully delivered, this delivery must clear the full remaining quantity."
            )

        if status == "partially_delivered" and delivered_quantity >= remaining_before_delivery:
            raise ValueError(
                "Use Fully Delivered or Short Closed when this delivery completes the remaining quantity."
            )

        if status == "short_closed" and total_after_delivery > purchase_request.ordered_quantity:
            raise ValueError(
                "Short-closed deliveries cannot exceed the ordered quantity."
            )

    submission = DeliverySubmission(
        requester=user,
        vendor=data["vendor"],
        currency=data["currency"],
        delivered_quantity=delivered_quantity,
        total_price=data["total_price"],
        purchase_request=purchase_request,
        status=status,
        notes=data.get("notes", ""),
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
