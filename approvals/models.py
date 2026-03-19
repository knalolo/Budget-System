"""
ApprovalLog model - generic audit trail for all approval actions.

Uses Django's contenttypes framework so a single model can record
approval history for any approvable object (PurchaseRequest,
PaymentRelease, etc.).
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

User = get_user_model()

ACTION_SUBMITTED = "submitted"
ACTION_PCM_APPROVED = "pcm_approved"
ACTION_PCM_REJECTED = "pcm_rejected"
ACTION_FINAL_APPROVED = "final_approved"
ACTION_FINAL_REJECTED = "final_rejected"
ACTION_STATUS_CHANGED = "status_changed"

ACTION_CHOICES = [
    (ACTION_SUBMITTED, "Submitted"),
    (ACTION_PCM_APPROVED, "PCM Approved"),
    (ACTION_PCM_REJECTED, "PCM Rejected"),
    (ACTION_FINAL_APPROVED, "Final Approved"),
    (ACTION_FINAL_REJECTED, "Final Rejected"),
    (ACTION_STATUS_CHANGED, "Status Changed"),
]


class ApprovalLog(models.Model):
    """Immutable audit record for every approval-related action."""

    # Generic relation - can point to any model instance
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_index=True,
    )
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    action_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="approval_actions",
    )
    comment = models.TextField(blank=True)

    # Status snapshot at the time of the action
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.action} by {self.action_by} "
            f"[{self.content_type} #{self.object_id}] "
            f"at {self.created_at:%Y-%m-%d %H:%M}"
        )
