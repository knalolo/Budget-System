"""Models for the deliveries app: DeliverySubmission."""

import logging

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
    total_price = models.DecimalField(max_digits=14, decimal_places=2)

    # --- Workflow status ---
    status = models.CharField(
        max_length=20,
        choices=settings.DELIVERY_STATUS_CHOICES,
        default="submitted",
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
        return self.status == "submitted"

    @property
    def is_saved(self) -> bool:
        return self.status == "saved"
