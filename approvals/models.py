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
    (ACTION_PCM_APPROVED, "Purchase Type Approval Approved"),
    (ACTION_PCM_REJECTED, "Purchase Type Approval Rejected"),
    (ACTION_FINAL_APPROVED, "Final Approver Approved"),
    (ACTION_FINAL_REJECTED, "Final Approver Rejected"),
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

    @property
    def human_action_label(self) -> str:
        """Return a user-facing action label aligned with the new approval naming."""
        first_stage_label = self._first_stage_role_label()
        action_map = {
            ACTION_SUBMITTED: "Submitted",
            ACTION_PCM_APPROVED: f"{first_stage_label} Approved",
            ACTION_PCM_REJECTED: f"{first_stage_label} Rejected",
            ACTION_FINAL_APPROVED: "Final Approver Approved",
            ACTION_FINAL_REJECTED: "Final Approver Rejected",
            ACTION_STATUS_CHANGED: "Status Changed",
        }
        return action_map.get(self.action, self.get_action_display())

    @property
    def old_status_display(self) -> str:
        """Return a user-facing label for the previous status."""
        return self._status_display(self.old_status)

    @property
    def new_status_display(self) -> str:
        """Return a user-facing label for the new status."""
        return self._status_display(self.new_status)

    def _first_stage_role_label(self) -> str:
        """Resolve the assigned Purchase Type approver label from the linked workflow object."""
        content_object = self.content_object
        return getattr(content_object, "first_approver_role_label", "Assigned Purchase Type Approver")

    def _status_display(self, status: str) -> str:
        """Map internal workflow status values to user-facing labels."""
        if not status:
            return ""

        status_map = {
            "draft": "Draft",
            "pending_pcm": f"Pending {self._first_stage_role_label()} Review",
            "pending_final": "Pending Final Approver Review",
            "approved": "Approved",
            "rejected": "Rejected",
            "po_sent": "Legacy PO Sent",
            "ordered": "Legacy Ordered",
            "completed": "Legacy Completed",
        }
        return status_map.get(status, status.replace("_", " ").title())
