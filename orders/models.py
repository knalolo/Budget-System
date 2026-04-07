"""Models for the orders app: Project, ExpenseCategory, and PurchaseRequest."""

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.services.request_number_service import generate_request_number

logger = logging.getLogger(__name__)

User = get_user_model()


class Project(models.Model):
    """An MC-numbered project that purchase requests are charged against."""

    mc_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mc_number"]

    def __str__(self) -> str:
        return f"{self.mc_number} - {self.name}"


class ExpenseCategory(models.Model):
    """A category used to classify project expenses (e.g., Prototype, Materials)."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Expense categories"

    def __str__(self) -> str:
        return self.name


class PurchaseRequest(models.Model):
    """A purchase request submitted by a requester for approval and procurement."""

    # --- Identity ---
    request_number = models.CharField(max_length=50, unique=True, blank=True)

    # --- Relationships ---
    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
    )

    # --- Request details ---
    description = models.TextField()
    vendor = models.CharField(max_length=255)
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
    )
    ordered_quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    justification = models.TextField()
    po_required = models.BooleanField(default=False)
    target_payment = models.CharField(max_length=50)

    # --- Workflow status ---
    status = models.CharField(
        max_length=20,
        choices=settings.PR_STATUS_CHOICES,
        default="draft",
    )

    # --- PCM approval ---
    pcm_approver = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pcm_reviewed_prs",
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
        related_name="final_reviewed_prs",
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
            self.request_number = generate_request_number("PR")
        super().save(*args, **kwargs)

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

    @property
    def requires_po(self) -> bool:
        """
        Return True when this PR's total price meets or exceeds the PO
        threshold configured in SystemConfig for its currency.

        Falls back to the stored po_required flag if no SystemConfig entry
        is found for the currency.
        """
        from core.models import SystemConfig  # local import avoids circular

        currency_key_map = {
            "SGD": "po_threshold_sgd",
            "USD": "po_threshold_usd",
            "EUR": "po_threshold_eur",
        }
        config_key = currency_key_map.get(self.currency)
        if config_key is None:
            return self.po_required

        threshold = SystemConfig.get_value(config_key)
        if threshold is None:
            return self.po_required

        try:
            return self.total_price >= threshold
        except TypeError:
            logger.warning(
                "PO threshold for %s (%r) is not numeric; falling back to po_required.",
                self.currency,
                threshold,
            )
            return self.po_required

    @property
    def unit_price(self) -> Decimal:
        if self.ordered_quantity <= 0:
            return Decimal("0.00")
        return self.total_price / Decimal(self.ordered_quantity)

    @property
    def delivered_quantity(self) -> int:
        delivered_total = self.delivery_submissions.aggregate(
            total=models.Sum("delivered_quantity")
        )["total"]
        return int(delivered_total or 0)

    @property
    def has_short_close(self) -> bool:
        return self.delivery_submissions.filter(status="short_closed").exists()

    @property
    def remaining_quantity(self) -> int:
        if self.has_short_close:
            return 0
        return max(self.ordered_quantity - self.delivered_quantity, 0)

    @property
    def delivery_stage_status(self) -> str:
        if self.status != "ordered":
            return self.status
        if self.has_short_close:
            return "short_closed"
        if self.delivered_quantity <= 0:
            return "do_pending"
        if self.remaining_quantity > 0:
            return "partially_delivered"
        if (
            self.remaining_payable_total <= Decimal("0.00")
            and self.payment_releases.filter(status="approved").exists()
        ):
            return "completed"
        if self.payment_releases.filter(
            status__in=("pending_pcm", "pending_final", "approved")
        ).exists():
            return "payment_in_progress"
        return "ready_for_payment"

    @property
    def delivery_stage_display(self) -> str:
        labels = {
            "do_pending": "Goods recieve Pending",
            "partially_delivered": "Partially Delivered",
            "ready_for_payment": "Ready for Payment",
            "short_closed": "Short Closed",
            "payment_in_progress": "Payment In Progress",
            "completed": "Completed",
        }
        return labels.get(self.delivery_stage_status, self.get_status_display())

    @property
    def available_standard_payment_quantity(self) -> int:
        requested_total = self.payment_releases.filter(
            payment_type="standard",
            status__in=("pending_pcm", "pending_final", "approved"),
        ).aggregate(total=models.Sum("payment_quantity"))["total"]
        requested_quantity = int(requested_total or 0)
        return max(self.delivered_quantity - requested_quantity, 0)

    @property
    def max_standard_payment_total(self) -> Decimal:
        return self.unit_price * Decimal(self.available_standard_payment_quantity)

    @property
    def active_payment_total(self) -> Decimal:
        requested_total = self.payment_releases.filter(
            status__in=("pending_pcm", "pending_final", "approved"),
        ).aggregate(total=models.Sum("total_price"))["total"]
        return requested_total or Decimal("0.00")

    @property
    def remaining_payable_total(self) -> Decimal:
        return max(self.total_price - self.active_payment_total, Decimal("0.00"))

    @property
    def is_ready_for_payment(self) -> bool:
        return (
            self.status == "ordered"
            and self.available_standard_payment_quantity > 0
            and self.remaining_payable_total > Decimal("0.00")
        )

    @property
    def has_delivery_records(self) -> bool:
        return self.delivery_submissions.exists()

    @property
    def latest_delivery_submission(self):
        return self.delivery_submissions.order_by("-created_at").first()
