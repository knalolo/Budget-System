"""Business logic services for the deliveries app (DeliverySubmission workflows)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.services.file_service import save_attachment

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.core.files.uploadedfile import UploadedFile

from .models import DeliverySubmission, DeliverySubmissionLineItem

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
    line_items = data.get("line_items", [])

    if purchase_request is not None:
        if purchase_request.status in ("approved", "po_sent"):
            from orders.services import mark_ordered

            purchase_request = mark_ordered(purchase_request)

        if line_items:
            _validate_delivery_line_items(purchase_request, line_items)
            delivered_quantity = sum(item["delivered_quantity"] for item in line_items)
            status = (
                "fully_delivered"
                if all(item["status"] == "fully_delivered" for item in line_items)
                else "partially_delivered"
            )
        else:
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
    _save_delivery_line_items(submission, line_items)

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


def _validate_delivery_line_items(purchase_request, line_items: list[dict]) -> None:
    """Validate per-line delivery quantities against the linked purchase request."""
    purchase_request_line_items = {
        item.id: item for item in purchase_request.line_items.all()
    }

    delivered_by_line_item = {}
    for submission in purchase_request.delivery_submissions.prefetch_related("line_items").all():
        for line in submission.line_items.all():
            key = line.purchase_request_line_item_id or line.sequence
            delivered_by_line_item[key] = delivered_by_line_item.get(key, 0) + line.delivered_quantity

    for index, line_item in enumerate(line_items, start=1):
        linked_line_id = line_item.get("purchase_request_line_item_id")
        if not linked_line_id or linked_line_id not in purchase_request_line_items:
            continue

        purchase_request_line = purchase_request_line_items[linked_line_id]
        remaining_quantity = max(
            purchase_request_line.quantity - delivered_by_line_item.get(linked_line_id, 0),
            0,
        )
        delivered_quantity = line_item["delivered_quantity"]
        status = line_item["status"]

        if delivered_quantity > remaining_quantity:
            raise ValueError(
                f"Line {index}: Actual delivered quantity cannot exceed the remaining quantity."
            )

        if status == "fully_delivered" and delivered_quantity != remaining_quantity:
            raise ValueError(
                f"Line {index}: Fully Delivered requires the full remaining quantity for that product."
            )

        if status == "partially_delivered" and delivered_quantity >= remaining_quantity:
            raise ValueError(
                f"Line {index}: Use Fully Delivered when this delivery completes the remaining quantity."
            )


def _save_delivery_line_items(submission: DeliverySubmission, line_items: list[dict]) -> None:
    """Persist delivery line items for the submission."""
    if not line_items:
        return

    DeliverySubmissionLineItem.objects.bulk_create(
        [
            DeliverySubmissionLineItem(
                delivery_submission=submission,
                purchase_request_line_item_id=item.get("purchase_request_line_item_id"),
                sequence=item["sequence"],
                product=item["product"],
                ordered_quantity=item["ordered_quantity"],
                delivered_quantity=item["delivered_quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                currency=item["currency"],
                status=item["status"],
            )
            for item in line_items
        ]
    )
