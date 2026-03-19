"""
Serializers for the approvals app.

ApprovalLogSerializer   - read-only representation of a log entry
ApprovalActionSerializer - validates an approve/reject action payload
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import ApprovalLog


class ApprovalLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for ApprovalLog records."""

    action_by_username = serializers.CharField(
        source="action_by.username",
        read_only=True,
    )
    action_by_full_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(
        source="get_action_display",
        read_only=True,
    )

    class Meta:
        model = ApprovalLog
        fields = [
            "id",
            "content_type",
            "object_id",
            "action",
            "action_display",
            "action_by",
            "action_by_username",
            "action_by_full_name",
            "comment",
            "old_status",
            "new_status",
            "created_at",
        ]
        read_only_fields = fields

    def get_action_by_full_name(self, obj: ApprovalLog) -> str:
        user = obj.action_by
        full_name = f"{user.first_name} {user.last_name}".strip()
        return full_name or user.username


class ApprovalActionSerializer(serializers.Serializer):
    """
    Validates a request body for approve/reject actions.

    Expected payload::

        {
            "decision": "approved" | "rejected",
            "comment": "optional free-text"
        }
    """

    VALID_DECISIONS = ("approved", "rejected")

    decision = serializers.ChoiceField(choices=VALID_DECISIONS)
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=2000,
    )

    def validate_decision(self, value: str) -> str:
        if value not in self.VALID_DECISIONS:
            raise serializers.ValidationError(
                f"'{value}' is not a valid decision. "
                f"Choose from: {', '.join(self.VALID_DECISIONS)}."
            )
        return value
