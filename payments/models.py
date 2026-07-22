"""Models for the payments app: PaymentRelease."""

import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.services.request_number_service import generate_request_number, to_workflow_number

logger = logging.getLogger(__name__)

User = get_user_model()
PURCHASE_REQUEST_NUMBER_RE = re.compile(r"^PR-(\d{8})-(\d{4})$")
PAYMENT_TYPE_STANDARD = "standard"
PAYMENT_TYPE_ADVANCE = "advance"
PAYMENT_TYPE_CHOICES = [
    (PAYMENT_TYPE_STANDARD, "Standard Payment"),
    (PAYMENT_TYPE_ADVANCE, "Advance Payment"),
]


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
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default=PAYMENT_TYPE_STANDARD,
    )
    payment_quantity = models.PositiveIntegerField(default=1)
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

    # --- First-stage approval (legacy pcm_* database columns) ---
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
        return f"{self.workflow_number} - {self.vendor}"

    @property
    def workflow_number(self) -> str:
        if self.purchase_request_id and self.purchase_request:
            return self.purchase_request.workflow_number
        return to_workflow_number(self.request_number)

    @property
    def installment_number(self) -> int | None:
        if not self.purchase_request_id or not self.pk:
            return None
        return self.purchase_request.payment_releases.filter(pk__lte=self.pk).count()

    @property
    def purchase_type(self) -> str:
        if self.purchase_request_id and self.purchase_request:
            return self.purchase_request.purchase_type
        return settings.PURCHASE_TYPE_PROJECT

    @property
    def first_approver_role_label(self) -> str:
        if self.purchase_request_id and self.purchase_request:
            return self.purchase_request.first_approver_role_label
        return "Approver"

    @property
    def first_approver(self):
        return self.pcm_approver

    @property
    def first_approval_decision(self) -> str:
        return self.pcm_decision

    @property
    def first_approval_decision_display(self) -> str:
        return dict(settings.DECISION_CHOICES).get(
            self.first_approval_decision,
            self.first_approval_decision,
        )

    @property
    def first_approval_comment(self) -> str:
        return self.pcm_comment

    @property
    def first_approved_at(self):
        return self.pcm_decided_at

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
    def is_submitted(self) -> bool:
        return self.status != "draft"

    @property
    def is_pending_approval(self) -> bool:
        return self.is_pending

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def is_rejected(self) -> bool:
        return self.status == "rejected"

    @property
    def human_status_label(self) -> str:
        labels = {
            "draft": "Draft",
            "pending_pcm": f"Pending {self.first_approver_role_label} Review",
            "pending_final": "Pending Final Approver Review",
            "approved": "Approved",
            "rejected": "Rejected",
        }
        return labels.get(self.status, self.get_status_display())

    @property
    def can_be_edited(self) -> bool:
        return self.status in ("draft", "rejected")

    @property
    def can_be_deleted(self) -> bool:
        return self.status == "draft"

    @property
    def is_advance_payment(self) -> bool:
        return self.payment_type == PAYMENT_TYPE_ADVANCE

    @property
    def has_goods_recieve(self) -> bool:
        if not self.purchase_request_id or not self.purchase_request:
            return False
        return self.purchase_request.delivered_quantity > 0

    @property
    def goods_recieve_progress_status(self) -> str:
        if not self.purchase_request_id or not self.purchase_request:
            return "unlinked"
        if self.is_advance_payment and self.purchase_request.delivered_quantity <= 0:
            return "advance_without_goods"
        if self.purchase_request.has_short_close:
            return "short_closed"
        if self.purchase_request.delivered_quantity <= 0:
            return "goods_pending"
        if self.purchase_request.remaining_quantity > 0:
            return "partially_received"
        return "goods_received"

    @property
    def goods_recieve_progress_label(self) -> str:
        labels = {
            "advance_without_goods": "Advance Payment • No Goods recieve",
            "goods_pending": "No Goods recieve Yet",
            "partially_received": "Partially Received",
            "goods_received": "Goods recieved",
            "short_closed": "Short Closed",
            "unlinked": "Manual Payment Link",
        }
        return labels.get(self.goods_recieve_progress_status, "Goods recieve")

    @property
    def goods_recieve_progress_badge_classes(self) -> str:
        badge_map = {
            "advance_without_goods": "bg-amber-100 text-amber-900 ring-amber-600/20",
            "goods_pending": "bg-rose-100 text-rose-800 ring-rose-600/20",
            "partially_received": "bg-sky-100 text-sky-800 ring-sky-600/20",
            "goods_received": "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
            "short_closed": "bg-slate-200 text-slate-800 ring-slate-500/20",
            "unlinked": "bg-gray-100 text-gray-700 ring-gray-500/20",
        }
        return badge_map.get(
            self.goods_recieve_progress_status,
            "bg-gray-100 text-gray-700 ring-gray-500/20",
        )

    @property
    def do_follow_up_required(self) -> bool:
        if not self.is_advance_payment or not self.is_approved:
            return False
        if not self.purchase_request_id or not self.purchase_request:
            return False
        return self.purchase_request.remaining_quantity > 0
