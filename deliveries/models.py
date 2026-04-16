"""Models for the deliveries app: DeliverySubmission."""

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.services.request_number_service import generate_request_number

logger = logging.getLogger(__name__)

User = get_user_model()


class DeliverySubmission(models.Model):
    """A delivery/sales-order document submission (no approval required)."""

    # --- Identity ---
    request_number = models.CharField(max_length=50, unique=True, blank=True)

    # --- Relationships ---
    purchase_request = models.ForeignKey(
        "orders.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_submissions",
    )
    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delivery_submissions",
    )

    # --- Submission details ---
    vendor = models.CharField(max_length=255)
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
    )
    delivered_quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)

    # --- Workflow status ---
    status = models.CharField(
        max_length=20,
        choices=settings.DELIVERY_STATUS_CHOICES,
        default="fully_delivered",
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Generic relations ---
    attachments = GenericRelation("core.FileAttachment")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.request_number} - {self.vendor}"

    # ------------------------------------------------------------------
    # Save override – auto-generate request_number
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs) -> None:
        if not self.request_number:
            self.request_number = generate_request_number("DO")
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Status properties
    # ------------------------------------------------------------------

    @property
    def is_submitted(self) -> bool:
        return self.status in ("partially_delivered", "fully_delivered", "short_closed")

    @property
    def is_saved(self) -> bool:
        return self.status == "saved"

    @property
    def is_partially_delivered(self) -> bool:
        return self.status == "partially_delivered"

    @property
    def is_fully_delivered(self) -> bool:
        return self.status == "fully_delivered"

    @property
    def is_short_closed(self) -> bool:
        return self.status == "short_closed"

    @property
    def requester_can_delete(self) -> bool:
        """
        Allow requester-side deletion only before approvers have acted on any
        linked payment release for the same purchase request.
        """
        if not self.purchase_request_id:
            return True

        return not self.purchase_request.payment_releases.exclude(
            status="draft"
        ).exists()

    @property
    def delivery_quantity_progress(self) -> str:
        if not self.purchase_request_id or not self.purchase_request:
            return str(self.delivered_quantity)
        if not self.is_partially_delivered:
            return str(self.delivered_quantity)
        return f"{self.delivered_quantity} / {self.purchase_request.ordered_quantity}"

    @property
    def delivery_value(self) -> Decimal:
        if not self.purchase_request_id or not self.purchase_request:
            return self.total_price
        return self.purchase_request.unit_price * Decimal(self.delivered_quantity)

    @property
    def delivery_value_progress(self) -> str:
        if not self.purchase_request_id or not self.purchase_request:
            return f"{self.currency} {self.total_price:.2f}"
        if not self.is_partially_delivered:
            return f"{self.currency} {self.total_price:.2f}"
        return (
            f"{self.currency} {self.delivery_value:.2f} / "
            f"{self.currency} {self.purchase_request.total_price:.2f}"
        )

    @property
    def display_line_items(self):
        line_items = list(self.line_items.all())
        if line_items:
            return line_items

        if self.purchase_request_id and self.purchase_request:
            return [
                {
                    "sequence": 1,
                    "product": self.purchase_request.description,
                    "ordered_quantity": self.purchase_request.ordered_quantity,
                    "delivered_quantity": self.delivered_quantity,
                    "unit_price": self.purchase_request.unit_price,
                    "total_price": self.total_price,
                    "currency": self.currency,
                    "status": self.status,
                }
            ]

        return [
            {
                "sequence": 1,
                "product": self.vendor,
                "ordered_quantity": self.delivered_quantity,
                "delivered_quantity": self.delivered_quantity,
                "unit_price": Decimal("0.00"),
                "total_price": self.total_price,
                "currency": self.currency,
                "status": self.status,
            }
        ]


class DeliverySubmissionLineItem(models.Model):
    """Individual delivered line items for a goods receive record."""

    delivery_submission = models.ForeignKey(
        DeliverySubmission,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    purchase_request_line_item = models.ForeignKey(
        "orders.PurchaseRequestLineItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_line_items",
    )
    sequence = models.PositiveIntegerField(default=1)
    product = models.CharField(max_length=255)
    ordered_quantity = models.PositiveIntegerField(default=1)
    delivered_quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
    )
    status = models.CharField(
        max_length=20,
        choices=(
            ("partially_delivered", "Partially Delivered"),
            ("fully_delivered", "Fully Delivered"),
        ),
        default="fully_delivered",
    )

    class Meta:
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        return f"{self.delivery_submission.request_number} - {self.product}"
