"""Models for the orders app: Project, ExpenseCategory, and PurchaseRequest."""

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.services.request_number_service import generate_request_number, to_workflow_number

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
    purchase_type = models.CharField(
        max_length=20,
        choices=settings.PURCHASE_TYPE_CHOICES,
        default=settings.PURCHASE_TYPE_PROJECT,
    )
    execution_mode = models.CharField(
        max_length=20,
        choices=settings.EXECUTION_MODE_CHOICES,
        default=settings.EXECUTION_MODE_DELIVERY_FIRST,
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

    # --- First-stage approval (legacy pcm_* database columns) ---
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
        return f"{self.workflow_number} - {self.vendor}"

    @property
    def workflow_number(self) -> str:
        return to_workflow_number(self.request_number)

    @property
    def purchase_type_display(self) -> str:
        return dict(settings.PURCHASE_TYPE_CHOICES).get(
            self.purchase_type,
            self.purchase_type,
        )

    @property
    def execution_mode_display(self) -> str:
        return dict(settings.EXECUTION_MODE_CHOICES).get(
            self.execution_mode,
            self.execution_mode,
        )

    @property
    def is_payment_first(self) -> bool:
        return self.execution_mode == settings.EXECUTION_MODE_PAYMENT_FIRST

    @property
    def is_delivery_first(self) -> bool:
        return self.execution_mode == settings.EXECUTION_MODE_DELIVERY_FIRST

    @property
    def first_approver_role_label(self) -> str:
        labels = {
            settings.PURCHASE_TYPE_PROJECT: "Project Approver",
            settings.PURCHASE_TYPE_NON_PROJECT: "Non-Project Approver",
            settings.PURCHASE_TYPE_OFFICE: "Office Approver",
        }
        return labels.get(self.purchase_type, "Approver")

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
    def human_status_label(self) -> str:
        labels = {
            "draft": "Draft",
            "pending_pcm": f"Pending {self.first_approver_role_label} Review",
            "pending_final": "Pending Final Approver Review",
            "approved": "Approved",
            "rejected": "Rejected",
            "po_sent": "Legacy PO Sent",
            "ordered": "Legacy Ordered",
            "completed": "Legacy Completed",
        }
        return labels.get(self.status, self.get_status_display())

    @property
    def can_be_edited(self) -> bool:
        return self.status in ("draft", "rejected")

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
    def is_execution_ready(self) -> bool:
        return self.status == "approved"

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
    def latest_payment_release(self):
        return (
            self.payment_releases.annotate(
                workflow_priority=models.Case(
                    models.When(status="approved", then=models.Value(50)),
                    models.When(status="pending_final", then=models.Value(40)),
                    models.When(status="pending_pcm", then=models.Value(30)),
                    models.When(status="draft", then=models.Value(20)),
                    models.When(status="rejected", then=models.Value(10)),
                    default=models.Value(0),
                    output_field=models.IntegerField(),
                )
            )
            .order_by("-workflow_priority", "-updated_at", "-created_at")
            .first()
        )

    @property
    def latest_submitted_payment_release(self):
        return (
            self.payment_releases.filter(
                status__in=("pending_pcm", "pending_final", "approved", "rejected")
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

    @property
    def latest_payment_draft(self):
        return (
            self.payment_releases.filter(status="draft")
            .order_by("-updated_at", "-created_at")
            .first()
        )

    @property
    def goods_stage(self) -> str:
        if self.has_short_close:
            return "short_closed"
        if not self.has_delivery_records:
            return "not_started"
        if self.remaining_quantity > 0:
            return "partially_delivered"
        return "fully_delivered"

    @property
    def goods_stage_display(self) -> str:
        labels = {
            "not_started": "Goods recieve Not Started",
            "partially_delivered": "Partially Delivered",
            "fully_delivered": "Fully Delivered",
            "short_closed": "Short Closed",
        }
        return labels.get(self.goods_stage, "Goods recieve")

    @property
    def payment_stage(self) -> str:
        payment = self.latest_payment_release
        if payment is None:
            return "not_started"
        return payment.status

    @property
    def payment_stage_display(self) -> str:
        labels = {
            "not_started": "Payment Not Started",
            "draft": "Payment Draft",
            "pending_pcm": f"Pending {self.first_approver_role_label} Review",
            "pending_final": "Pending Final Approver Review",
            "approved": "Payment Approved",
            "rejected": "Payment Rejected",
        }
        return labels.get(self.payment_stage, "Payment")

    @property
    def workflow_completed(self) -> bool:
        return (
            self.status == "approved"
            and self.payment_stage == "approved"
            and self.goods_stage in ("fully_delivered", "short_closed")
        )

    @property
    def workflow_stage(self) -> str:
        if self.is_draft:
            return "draft"
        if self.is_pending:
            return "awaiting_pr_approval"
        if self.is_rejected:
            return "rejected"
        if self.workflow_completed:
            return "completed"
        if not self.is_execution_ready:
            return self.status

        goods_stage = self.goods_stage
        payment_stage = self.payment_stage

        if self.is_payment_first:
            if payment_stage in ("not_started", "draft", "rejected"):
                return "payment_pending"
            if payment_stage != "approved":
                return "awaiting_payment_approval"
            if goods_stage == "not_started":
                return "goods_pending"
            if goods_stage == "partially_delivered":
                return "goods_follow_up_required"
            return "completed" if self.workflow_completed else "goods_pending"

        if goods_stage == "not_started":
            return "goods_pending"
        if goods_stage == "partially_delivered":
            return "goods_follow_up_required"
        if payment_stage in ("not_started", "draft", "rejected"):
            return "payment_pending"
        return "awaiting_payment_approval"

    @property
    def workflow_stage_display(self) -> str:
        labels = {
            "draft": "Draft",
            "awaiting_pr_approval": f"Awaiting {self.first_approver_role_label} / Final Approver Approval",
            "rejected": "Rejected",
            "ready_for_execution": "Choose Next Step",
            "goods_pending": "Goods recieve Still Required",
            "payment_pending": "Payment Still Required",
            "goods_follow_up_required": "Partial Delivery Follow-up",
            "awaiting_payment_approval": f"Waiting For {self.first_approver_role_label} / Final Approver",
            "completed": "Completed",
        }
        return labels.get(self.workflow_stage, self.get_status_display())

    @property
    def can_submit_goods(self) -> bool:
        if (
            not self.is_execution_ready
            or self.goods_stage in ("fully_delivered", "short_closed")
        ):
            return False
        if self.is_payment_first:
            return self.payment_stage == "approved"
        return True

    @property
    def can_submit_payment(self) -> bool:
        if not self.is_execution_ready or self.payment_stage not in (
            "not_started",
            "draft",
            "rejected",
        ):
            return False
        if self.is_payment_first:
            return self.goods_stage == "not_started"
        return self.delivered_quantity > 0

    @property
    def delivery_stage_status(self) -> str:
        if not self.is_execution_ready:
            return self.status
        if self.workflow_completed:
            return "completed"
        if self.goods_stage == "short_closed":
            return "short_closed"
        if self.goods_stage == "not_started":
            return "do_pending"
        if self.goods_stage == "partially_delivered":
            return "partially_delivered"
        if self.payment_stage in ("draft", "pending_pcm", "pending_final", "approved"):
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
    def delivered_total_value(self) -> Decimal:
        from deliveries.models import DeliverySubmissionLineItem

        line_item_total = DeliverySubmissionLineItem.objects.filter(
            delivery_submission__purchase_request=self
        ).aggregate(total=models.Sum("total_price"))["total"] or Decimal("0.00")
        submission_total = self.delivery_submissions.filter(
            line_items__isnull=True
        ).aggregate(total=models.Sum("total_price"))["total"] or Decimal("0.00")
        return line_item_total + submission_total

    @property
    def active_standard_payment_total(self) -> Decimal:
        requested_total = self.payment_releases.filter(
            payment_type="standard",
            status__in=("pending_pcm", "pending_final", "approved"),
        ).aggregate(total=models.Sum("total_price"))["total"]
        return requested_total or Decimal("0.00")

    @property
    def available_standard_payment_total(self) -> Decimal:
        return max(
            self.delivered_total_value - self.active_standard_payment_total,
            Decimal("0.00"),
        )

    @property
    def max_standard_payment_total(self) -> Decimal:
        return min(self.available_standard_payment_total, self.remaining_payable_total)

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
            self.is_execution_ready
            and self.available_standard_payment_quantity > 0
            and self.remaining_payable_total > Decimal("0.00")
        )

    @property
    def has_delivery_records(self) -> bool:
        return self.delivery_submissions.exists()

    @property
    def latest_delivery_submission(self):
        return self.delivery_submissions.order_by("-created_at").first()

    @property
    def latest_open_delivery_submission(self):
        return self.delivery_submissions.filter(status="partially_delivered").order_by("-created_at").first()

    @property
    def display_line_items(self):
        line_items = list(self.line_items.all())
        if line_items:
            return line_items
        return [
            {
                "sequence": 1,
                "product": self.description,
                "quantity": self.ordered_quantity,
                "unit_price": self.unit_price,
                "total_price": self.total_price,
                "currency": self.currency,
            }
        ]


class PurchaseRequestLineItem(models.Model):
    """Individual line items belonging to a purchase request."""

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    sequence = models.PositiveIntegerField(default=1)
    product = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
    )

    class Meta:
        ordering = ["sequence", "id"]

    def __str__(self) -> str:
        return f"{self.purchase_request.workflow_number} - {self.product}"
