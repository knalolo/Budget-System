"""DRF serializers for PaymentRelease."""
from __future__ import annotations

from rest_framework import serializers

from approvals.serializers import ApprovalLogSerializer
from core.models import FileAttachment

from .models import PaymentRelease


# ---------------------------------------------------------------------------
# Nested helpers
# ---------------------------------------------------------------------------

class _AttachmentSerializer(serializers.ModelSerializer):
    """Lightweight read-only attachment representation."""

    class Meta:
        model = FileAttachment
        fields = [
            "id",
            "original_filename",
            "file_type",
            "file_size",
            "file",
            "uploaded_by",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# List serializer (lightweight)
# ---------------------------------------------------------------------------

class PaymentReleaseListSerializer(serializers.ModelSerializer):
    """Minimal fields for list views and embedded representations."""

    requester_username = serializers.CharField(
        source="requester.username",
        read_only=True,
    )
    requester_full_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    currency_display = serializers.CharField(
        source="get_currency_display",
        read_only=True,
    )

    class Meta:
        model = PaymentRelease
        fields = [
            "id",
            "request_number",
            "requester",
            "requester_username",
            "requester_full_name",
            "vendor",
            "currency",
            "currency_display",
            "total_price",
            "status",
            "status_display",
            "created_at",
        ]
        read_only_fields = fields

    def get_requester_full_name(self, obj: PaymentRelease) -> str:
        user = obj.requester
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.username


# ---------------------------------------------------------------------------
# Detail serializer (full)
# ---------------------------------------------------------------------------

class PaymentReleaseDetailSerializer(serializers.ModelSerializer):
    """Full representation including approval fields, attachments, and logs."""

    requester_username = serializers.CharField(
        source="requester.username",
        read_only=True,
    )
    requester_full_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    currency_display = serializers.CharField(
        source="get_currency_display",
        read_only=True,
    )
    pcm_approver_username = serializers.SerializerMethodField()
    final_approver_username = serializers.SerializerMethodField()
    attachments = _AttachmentSerializer(many=True, read_only=True)
    approval_logs = ApprovalLogSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentRelease
        fields = [
            "id",
            "request_number",
            "purchase_request",
            "requester",
            "requester_username",
            "requester_full_name",
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "currency_display",
            "total_price",
            "justification",
            "po_number",
            "target_payment",
            "status",
            "status_display",
            # PCM approval
            "pcm_approver",
            "pcm_approver_username",
            "pcm_decision",
            "pcm_comment",
            "pcm_decided_at",
            # Final approval
            "final_approver",
            "final_approver_username",
            "final_decision",
            "final_comment",
            "final_decided_at",
            # Timestamps
            "created_at",
            "updated_at",
            # Nested
            "attachments",
            "approval_logs",
        ]
        read_only_fields = fields

    def get_requester_full_name(self, obj: PaymentRelease) -> str:
        user = obj.requester
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.username

    def get_pcm_approver_username(self, obj: PaymentRelease) -> str | None:
        if obj.pcm_approver:
            return obj.pcm_approver.username
        return None

    def get_final_approver_username(self, obj: PaymentRelease) -> str | None:
        if obj.final_approver:
            return obj.final_approver.username
        return None


# ---------------------------------------------------------------------------
# Create / write serializer
# ---------------------------------------------------------------------------

class PaymentReleaseCreateSerializer(serializers.ModelSerializer):
    """Write serializer used when creating or updating a PaymentRelease."""

    class Meta:
        model = PaymentRelease
        fields = [
            "purchase_request",
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "total_price",
            "justification",
            "po_number",
            "target_payment",
        ]

    def validate_total_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Total price must be greater than zero.")
        return value

    def validate_po_number(self, value):
        cleaned = value.strip() if value else ""
        if not cleaned:
            raise serializers.ValidationError("PO number is required. Use 'N/A' if not applicable.")
        return cleaned
