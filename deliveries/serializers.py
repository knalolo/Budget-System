"""DRF serializers for DeliverySubmission."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.models import FileAttachment
from .models import DeliverySubmission

User = get_user_model()


class _RequesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]


class _AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = [
            "id",
            "original_filename",
            "file_type",
            "file_size",
            "file",
            "created_at",
        ]


class DeliverySubmissionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    request_number = serializers.CharField(source="workflow_number", read_only=True)
    requester = _RequesterSerializer(read_only=True)

    class Meta:
        model = DeliverySubmission
        fields = [
            "id",
            "request_number",
            "requester",
            "vendor",
            "currency",
            "delivered_quantity",
            "total_price",
            "status",
            "created_at",
        ]


class DeliverySubmissionDetailSerializer(serializers.ModelSerializer):
    """Full serializer including attachments."""

    request_number = serializers.CharField(source="workflow_number", read_only=True)
    requester = _RequesterSerializer(read_only=True)
    attachments = _AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = DeliverySubmission
        fields = [
            "id",
            "request_number",
            "purchase_request",
            "requester",
            "vendor",
            "currency",
            "delivered_quantity",
            "total_price",
            "status",
            "notes",
            "attachments",
            "created_at",
            "updated_at",
        ]


class DeliverySubmissionCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating a DeliverySubmission."""

    class Meta:
        model = DeliverySubmission
        fields = [
            "purchase_request",
            "vendor",
            "currency",
            "delivered_quantity",
            "total_price",
            "status",
            "notes",
        ]

    def validate_total_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total price must be greater than zero.")
        return value
