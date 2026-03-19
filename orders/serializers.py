"""DRF serializers for Project, ExpenseCategory, and PurchaseRequest."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from approvals.serializers import ApprovalLogSerializer

from .models import ExpenseCategory, Project, PurchaseRequest

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared nested serializers
# ---------------------------------------------------------------------------


class UserBriefSerializer(serializers.ModelSerializer):
    """Minimal user representation for embedding in other serializers."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]
        read_only_fields = fields


class ProjectBriefSerializer(serializers.ModelSerializer):
    """Minimal project representation for embedding in other serializers."""

    class Meta:
        model = Project
        fields = ["id", "mc_number", "name"]
        read_only_fields = fields


class ExpenseCategoryBriefSerializer(serializers.ModelSerializer):
    """Minimal expense-category representation for embedding."""

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Project / ExpenseCategory
# ---------------------------------------------------------------------------


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for the Project model."""

    class Meta:
        model = Project
        fields = ["id", "mc_number", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Serializer for the ExpenseCategory model."""

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


# ---------------------------------------------------------------------------
# PurchaseRequest serializers
# ---------------------------------------------------------------------------


class PurchaseRequestListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    requester = UserBriefSerializer(read_only=True)
    expense_category = ExpenseCategoryBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = [
            "id",
            "request_number",
            "requester",
            "expense_category",
            "project",
            "vendor",
            "currency",
            "total_price",
            "po_required",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class PurchaseRequestDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail, create, and update views."""

    requester = UserBriefSerializer(read_only=True)
    expense_category = ExpenseCategoryBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)
    pcm_approver = UserBriefSerializer(read_only=True)
    final_approver = UserBriefSerializer(read_only=True)

    # Lazy import to avoid a circular dependency at module load time.
    attachments = serializers.SerializerMethodField()
    approval_logs = ApprovalLogSerializer(many=True, read_only=True)

    # Write-only FK fields (accepted as integer PKs on create/update)
    expense_category_id = serializers.PrimaryKeyRelatedField(
        queryset=ExpenseCategory.objects.all(),
        source="expense_category",
        write_only=True,
    )
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        source="project",
        write_only=True,
    )

    class Meta:
        model = PurchaseRequest
        fields = [
            "id",
            "request_number",
            "requester",
            # write FK inputs
            "expense_category_id",
            "project_id",
            # nested read representations
            "expense_category",
            "project",
            # request details
            "description",
            "vendor",
            "currency",
            "total_price",
            "justification",
            "po_required",
            "target_payment",
            # workflow
            "status",
            # PCM approval
            "pcm_approver",
            "pcm_decision",
            "pcm_comment",
            "pcm_decided_at",
            # final approval
            "final_approver",
            "final_decision",
            "final_comment",
            "final_decided_at",
            # related objects
            "attachments",
            "approval_logs",
            # timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "request_number",
            "requester",
            "status",
            "pcm_approver",
            "pcm_decision",
            "pcm_comment",
            "pcm_decided_at",
            "final_approver",
            "final_decision",
            "final_comment",
            "final_decided_at",
            "attachments",
            "approval_logs",
            "created_at",
            "updated_at",
        ]

    def get_attachments(self, obj: PurchaseRequest):
        from core.serializers import FileAttachmentSerializer  # avoid circular import

        qs = obj.attachments.all()
        return FileAttachmentSerializer(qs, many=True, context=self.context).data


class PurchaseRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer used exclusively for creating new purchase requests."""

    expense_category = serializers.PrimaryKeyRelatedField(
        queryset=ExpenseCategory.objects.all()
    )
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = PurchaseRequest
        fields = [
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "total_price",
            "justification",
            "po_required",
            "target_payment",
        ]

    def create(self, validated_data: dict) -> PurchaseRequest:
        request = self.context["request"]
        return PurchaseRequest.objects.create(
            requester=request.user,
            **validated_data,
        )
