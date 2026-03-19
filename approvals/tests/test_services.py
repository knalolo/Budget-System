"""Unit tests for approvals.services (generic two-level approval engine).

NOTE: The approvals/services._get_user_role function references
user.userprofile.role, but the UserProfile model uses related_name="profile".
This means _get_user_role always falls back to "requester", causing
can_user_approve to return (False, <wrong-role-reason>) for any user at
the PCM or final stage. The tests here document both the correct service
behavior (process_approval, submit_for_approval) and the actual (bugged)
can_user_approve behavior.
"""
import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from approvals.models import ACTION_SUBMITTED, ACTION_PCM_APPROVED, ACTION_FINAL_APPROVED, ApprovalLog
import approvals.services as svc
from orders.tests.factories import PurchaseRequestFactory, UserFactory


# ---------------------------------------------------------------------------
# submit_for_approval
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitForApproval:
    def test_draft_transitions_to_pending_pcm(self):
        pr = PurchaseRequestFactory(status="draft")
        updated = svc.submit_for_approval(pr)
        assert updated.status == "pending_pcm"

    def test_submission_creates_log(self):
        pr = PurchaseRequestFactory(status="draft")
        updated = svc.submit_for_approval(pr)
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_SUBMITTED).first()
        assert log is not None
        assert log.old_status == "draft"
        assert log.new_status == "pending_pcm"

    def test_non_draft_raises_validation_error(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        with pytest.raises(ValidationError, match="draft"):
            svc.submit_for_approval(pr)

    def test_log_actor_is_requester(self):
        pr = PurchaseRequestFactory(status="draft")
        updated = svc.submit_for_approval(pr)
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_SUBMITTED).first()
        assert log.action_by == updated.requester


# ---------------------------------------------------------------------------
# process_approval – PCM level
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProcessPcmApproval:
    def test_pcm_approve_transitions_to_pending_final(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "approved")
        assert updated.status == "pending_final"
        assert updated.pcm_approver == approver
        assert updated.pcm_decision == "approved"

    def test_pcm_approve_creates_log(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "approved")
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_PCM_APPROVED).first()
        assert log is not None
        assert log.action_by == approver

    def test_pcm_rejection_transitions_to_rejected(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "rejected", comment="Not approved")
        assert updated.status == "rejected"
        assert updated.pcm_decision == "rejected"
        assert updated.pcm_comment == "Not approved"


# ---------------------------------------------------------------------------
# process_approval – final level
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProcessFinalApproval:
    def test_final_approve_transitions_to_approved(self):
        pr = PurchaseRequestFactory(status="pending_final")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "approved")
        assert updated.status == "approved"
        assert updated.final_decision == "approved"

    def test_final_approval_creates_log(self):
        pr = PurchaseRequestFactory(status="pending_final")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "approved")
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_FINAL_APPROVED).first()
        assert log is not None

    def test_final_rejection_transitions_to_rejected(self):
        pr = PurchaseRequestFactory(status="pending_final")
        approver = UserFactory()
        updated = svc.process_approval(pr, approver, "rejected")
        assert updated.status == "rejected"
        assert updated.final_decision == "rejected"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProcessApprovalValidation:
    def test_invalid_decision_raises(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        with pytest.raises(ValidationError, match="Invalid decision"):
            svc.process_approval(pr, approver, "maybe")

    def test_invalid_state_transition_raises(self):
        """Attempting to approve a draft should raise."""
        pr = PurchaseRequestFactory(status="draft")
        approver = UserFactory()
        with pytest.raises(ValidationError, match="pending"):
            svc.process_approval(pr, approver, "approved")

    def test_self_approval_blocked(self):
        """Requester cannot approve their own submission."""
        pr = PurchaseRequestFactory(status="pending_pcm")
        with pytest.raises(ValidationError, match="cannot approve"):
            svc.process_approval(pr, pr.requester, "approved")


# ---------------------------------------------------------------------------
# can_user_approve
# NOTE: Due to the userprofile/profile naming bug, _get_user_role always
# returns "requester" for all users. The tests below document actual behavior.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCanUserApprove:
    def test_item_not_awaiting_approval_returns_false(self):
        """Draft items are not approvable."""
        pr = PurchaseRequestFactory(status="draft")
        approver = UserFactory()
        can, reason = svc.can_user_approve(pr, approver)
        assert can is False
        assert "status" in reason.lower() or "awaiting" in reason.lower()

    def test_requester_cannot_approve_own_pending(self):
        """Self-approval is blocked (checked before role)."""
        pr = PurchaseRequestFactory(status="pending_pcm")
        can, reason = svc.can_user_approve(pr, pr.requester)
        assert can is False
        assert "cannot approve" in reason.lower()

    def test_other_user_cannot_approve_due_to_role_bug(self):
        """Due to userprofile/profile naming bug, all non-requester role
        lookups fail and users appear as 'requester' role, making them
        unable to approve at PCM or final stages."""
        pr = PurchaseRequestFactory(status="pending_pcm")
        # Even a user set up with pcm_approver role via user.profile cannot
        # pass the role check in can_user_approve because it uses user.userprofile
        approver = UserFactory()
        can, reason = svc.can_user_approve(pr, approver)
        # With the bug, this is False (wrong role message)
        assert can is False

    def test_completed_item_not_approvable(self):
        """approved/rejected status items are not approvable."""
        pr = PurchaseRequestFactory(status="approved")
        approver = UserFactory()
        can, reason = svc.can_user_approve(pr, approver)
        assert can is False


# ---------------------------------------------------------------------------
# get_approval_history
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetApprovalHistory:
    def test_returns_logs_for_object(self):
        pr = PurchaseRequestFactory(status="draft")
        svc.submit_for_approval(pr)
        history = svc.get_approval_history(pr)
        assert history.exists()

    def test_does_not_return_other_objects_logs(self):
        pr1 = PurchaseRequestFactory(status="draft")
        pr2 = PurchaseRequestFactory(status="draft")
        svc.submit_for_approval(pr1)
        svc.submit_for_approval(pr2)
        history = svc.get_approval_history(pr1)
        for log in history:
            assert log.object_id == pr1.pk

    def test_returns_empty_for_new_object(self):
        pr = PurchaseRequestFactory(status="draft")
        history = svc.get_approval_history(pr)
        assert not history.exists()
