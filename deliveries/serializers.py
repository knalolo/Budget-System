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

    requester = _RequesterSerializer(read_only=True)

    class Meta:
        model = DeliverySubmission
        fields = [
            "id",
            "request_number",
            "requester",
            "vendor",
            "currency",
            "total_price",
            "status",
            "created_at",
        ]


class DeliverySubmissionDetailSerializer(serializers.ModelSerializer):
    """Full serializer including attachments."""

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
            "total_price",
            "status",
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
            "total_price",
        ]

    def validate_total_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total price must be greater than zero.")
        return value
