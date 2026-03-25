"""Models for the payments app: PaymentRelease."""

import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.services.request_number_service import generate_request_number

logger = logging.getLogger(__name__)

User = get_user_model()
PURCHASE_REQUEST_NUMBER_RE = re.compile(r"^PR-(\d{8})-(\d{4})$")


class PaymentRelease(models.Model):
    """A payment release request submitted for vendor invoice payment."""

    # --- Identity ---
    request_number = models.CharField(max_length=50, unique=True, blank=True)

    # --- Relationships ---
    purchase_request = models.ForeignKey(
        "orders.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_releases",
    )
    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payment_releases",
    )
    expense_category = models.ForeignKey(
        "orders.ExpenseCategory",
        on_delete=models.PROTECT,
    )
    project = models.ForeignKey(
        "orders.Project",
        on_delete=models.PROTECT,
    )

    # --- Request details ---
    description = models.TextField()
    vendor = models.CharField(max_length=255)
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
    )
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    justification = models.TextField()
    po_number = models.CharField(
        max_length=50,
        help_text='Either "N/A" or a specific PO number.',
    )
    target_payment = models.CharField(max_length=50)

    # --- Workflow status ---
    status = models.CharField(
        max_length=20,
        choices=settings.PAYMENT_STATUS_CHOICES,
        default="draft",
    )

    # --- PCM approval ---
    pcm_approver = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pcm_reviewed_payments",
    )
    pcm_decision = models.CharField(
        max_length=20,
        choices=settings.DECISION_CHOICES,
        default="pending",
    )
    pcm_comment = models.TextField(blank=True)
    pcm_decided_at = models.DateTimeField(null=True, blank=True)

    # --- Final approval ---
    final_approver = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="final_reviewed_payments",
    )
    final_decision = models.CharField(
        max_length=20,
        choices=settings.DECISION_CHOICES,
        default="pending",
    )
    final_comment = models.TextField(blank=True)
    final_decided_at = models.DateTimeField(null=True, blank=True)

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Generic relations ---
    attachments = GenericRelation("core.FileAttachment")
    approval_logs = GenericRelation("approvals.ApprovalLog")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.request_number} - {self.vendor}"

    # ------------------------------------------------------------------
    # Save override – auto-generate request_number
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs) -> None:
        if not self.request_number:
            self.request_number = self._generate_request_number()
        super().save(*args, **kwargs)

    def _generate_request_number(self) -> str:
        """Prefer the linked purchase-request sequence when available."""
        if self.purchase_request_id and self.purchase_request:
            match = PURCHASE_REQUEST_NUMBER_RE.match(
                self.purchase_request.request_number or ""
            )
            if match:
                synced_number = f"RP-{match.group(1)}-{match.group(2)}"
                if not PaymentRelease.objects.filter(
                    request_number=synced_number
                ).exists():
                    return synced_number

        return generate_request_number("RP")

    # ------------------------------------------------------------------
    # Status properties
    # ------------------------------------------------------------------

    @property
    def is_draft(self) -> bool:
        return self.status == "draft"

    @property
    def is_pending(self) -> bool:
        return self.status in ("pending_pcm", "pending_final")

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def is_rejected(self) -> bool:
        return self.status == "rejected"

    @property
    def can_be_edited(self) -> bool:
        return self.status == "draft"

    @property
    def can_be_deleted(self) -> bool:
        return self.status == "draft"
