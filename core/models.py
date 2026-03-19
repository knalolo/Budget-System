from django.db import models

# Create your models here.
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProjectStatus(models.TextChoices):
    DRAFT = "Draft", "Draft"
    ACTIVE = "Active", "Active"
    CLOSED = "Closed", "Closed"


class PORequestStatus(models.TextChoices):
    DRAFT = "Draft", "Draft"
    SUBMITTED = "Submitted", "Submitted"
    APPROVED = "Approved", "Approved"
    REJECTED = "Rejected", "Rejected"


class UserRole(models.TextChoices):
    REQUESTER = "requester", "Requester"
    APPROVER = "approver", "Approver"
    ADMIN = "admin", "Admin"


class Project(TimeStampedModel):
    project_code = models.CharField(max_length=50, unique=True)
    project_name = models.CharField(max_length=255)
    project_manager = models.CharField(max_length=255, blank=True)
    project_owner = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
    )

    class Meta:
        ordering = ["project_code"]

    def __str__(self) -> str:
        return f"{self.project_code} - {self.project_name}"

    @property
    def total_approved_budget(self) -> Decimal:
        total = self.budgets.aggregate(total=models.Sum("approved_budget"))["total"]
        return total or Decimal("0.00")

    @property
    def total_actual_spent(self) -> Decimal:
        total = self.budgets.aggregate(total=models.Sum("actual_spent"))["total"]
        return total or Decimal("0.00")

    @property
    def total_remaining_budget(self) -> Decimal:
        return self.total_approved_budget - self.total_actual_spent


class CostItem(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class ProjectBudget(TimeStampedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="budgets",
    )
    cost_item = models.ForeignKey(
        CostItem,
        on_delete=models.PROTECT,
        related_name="project_budgets",
    )

    internal_hours = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    internal_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    external_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    approved_budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    actual_spent = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)

    class Meta:
        unique_together = ("project", "cost_item")
        ordering = ["project", "cost_item__sort_order", "cost_item__code"]

    def __str__(self) -> str:
        return f"{self.project.project_code} - {self.cost_item.name}"

    @property
    def remaining_budget(self) -> Decimal:
        return (self.approved_budget or Decimal("0.00")) - (
            self.actual_spent or Decimal("0.00")
        )

    def save(self, *args, **kwargs):
        # 如果 approved_budget 还没填，就用 internal_cost + external_cost 自动带出
        if self.approved_budget in (None, Decimal("0"), Decimal("0.00")):
            self.approved_budget = (self.internal_cost or Decimal("0.00")) + (
                self.external_cost or Decimal("0.00")
            )
        super().save(*args, **kwargs)


class UserProfile(TimeStampedModel):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.REQUESTER,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.role})"


class PORequest(TimeStampedModel):
    request_no = models.CharField(max_length=50, unique=True)

    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="po_requests",
    )

    cost_item = models.ForeignKey(
        CostItem,
        on_delete=models.PROTECT,
        related_name="po_requests",
    )

    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField(blank=True)

    supplier_name = models.CharField(max_length=255)
    description = models.TextField()

    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    currency = models.CharField(max_length=10, default="EUR")
    needed_date = models.DateField(null=True, blank=True)
    request_date = models.DateField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=PORequestStatus.choices,
        default=PORequestStatus.DRAFT,
    )

    approver_name = models.CharField(max_length=255, blank=True)
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_comment = models.TextField(blank=True)

    over_budget_flag = models.BooleanField(default=False)
    attachment_path = models.CharField(max_length=500, blank=True)

    def save(self, *args, **kwargs):
        print("🔥 SAVE FUNCTION CALLED")

        super().save(*args, **kwargs)

        print("Status =", self.status)

        # 注意：这里用枚举值
        if self.status == PORequestStatus.APPROVED:
            print("✅ APPROVED detected")

            try:
                budget = ProjectBudget.objects.get(
                    project=self.project,
                    cost_item=self.cost_item
                )

                print("🎯 Budget FOUND:", budget)

                budget.actual_spent += self.amount
                budget.save()

                print("💰 Budget UPDATED")

            except ProjectBudget.DoesNotExist:
                print("❌ Budget NOT FOUND")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.request_no

    def clean(self):
        if self.quantity is not None and self.unit_price is not None:
            calculated_amount = (self.quantity or Decimal("0.00")) * (
                self.unit_price or Decimal("0.00")
            )
            if self.amount and self.amount != calculated_amount:
                # V1 简化：允许 amount 手填，但要保证不为负
                if self.amount < 0:
                    raise ValidationError("Amount cannot be negative.")
            elif not self.amount or self.amount == Decimal("0.00"):
                self.amount = calculated_amount

        if self.amount < 0:
            raise ValidationError("Amount cannot be negative.")

    def save(self, *args, **kwargs):
        if (not self.amount or self.amount == Decimal("0.00")) and self.quantity is not None and self.unit_price is not None:
            self.amount = (self.quantity or Decimal("0.00")) * (
                self.unit_price or Decimal("0.00")
            )

        # 自动检查是否超预算
        budget = ProjectBudget.objects.filter(
            project=self.project,
            cost_item=self.cost_item,
        ).first()

        if budget:
            self.over_budget_flag = self.amount > budget.remaining_budget
        else:
            self.over_budget_flag = True

        super().save(*args, **kwargs)

    def apply_approval_to_budget(self):
        """
        当 PO 审批通过后，直接记入 actual_spent
        """
        if self.status != PORequestStatus.APPROVED:
            return

        budget = ProjectBudget.objects.filter(
            project=self.project,
            cost_item=self.cost_item,
        ).first()

        if not budget:
            raise ValidationError("No matching project budget found.")

        # 防止重复累计：只有首次批准才加
        if not ApprovalLog.objects.filter(
            po_request=self,
            action="ApproveApplied"
        ).exists():
            budget.actual_spent = (budget.actual_spent or Decimal("0.00")) + (
                self.amount or Decimal("0.00")
            )
            budget.save()

            ApprovalLog.objects.create(
                po_request=self,
                action="ApproveApplied",
                action_by=self.approver_name or "System",
                comment=f"Applied amount {self.amount} to actual spent.",
            )


class ApprovalLog(TimeStampedModel):
    po_request = models.ForeignKey(
        PORequest,
        on_delete=models.CASCADE,
        related_name="approval_logs",
    )
    action = models.CharField(max_length=50)
    action_by = models.CharField(max_length=255)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.po_request.request_no} - {self.action}"