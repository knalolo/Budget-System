"""Unit tests for approvals.services."""
import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from approvals.models import (
    ACTION_FIRST_STAGE_APPROVED,
    ACTION_FINAL_APPROVED,
    ACTION_SUBMITTED,
    ApprovalLog,
)
import approvals.services as svc
from orders.tests.factories import PurchaseRequestFactory, UserFactory


# ---------------------------------------------------------------------------
# submit_for_approval
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitForApproval:
    def test_draft_transitions_to_pending_pcm(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        updated = svc.submit_for_approval(pr)
        assert updated.status == "pending_pcm"

    def test_submission_creates_log(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        updated = svc.submit_for_approval(pr)
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_SUBMITTED).first()
        assert log.action_by == updated.requester

    def test_missing_purchase_type_approver_raises(self):
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft", purchase_type="project")

        with pytest.raises(ValidationError, match="Project Approver"):
            svc.submit_for_approval(pr)

    def test_missing_final_approver_raises(self):
        UserFactory(project_approver=True)
        pr = PurchaseRequestFactory(status="draft", purchase_type="project")

        with pytest.raises(ValidationError, match="Final Approver"):
            svc.submit_for_approval(pr)


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
        log = ApprovalLog.objects.filter(object_id=updated.pk, action=ACTION_FIRST_STAGE_APPROVED).first()
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

    def test_requester_with_matching_approver_permission_can_self_approve(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        pr.requester.profile.apply_permission_flags(
            is_requester=True,
            is_project_approver=True,
        )
        pr.requester.profile.save()

        updated = svc.process_approval(pr, pr.requester, "approved")

        assert updated.status == "pending_final"
        assert updated.pcm_approver == pr.requester


# ---------------------------------------------------------------------------
# can_user_approve
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
        """A requester-only account still cannot approve without approver permission."""
        pr = PurchaseRequestFactory(status="pending_pcm")
        can, reason = svc.can_user_approve(pr, pr.requester)
        assert can is False
        assert "project approver" in reason.lower()

    def test_matching_project_approver_can_approve_first_stage(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory(project_approver=True)
        can, reason = svc.can_user_approve(pr, approver)
        assert can is True
        assert "may approve" in reason.lower()

    def test_matching_non_project_approver_can_approve_first_stage(self):
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="non_project")
        approver = UserFactory(non_project_approver=True)
        can, reason = svc.can_user_approve(pr, approver)
        assert can is True
        assert "may approve" in reason.lower()

    def test_matching_office_approver_can_approve_first_stage(self):
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="office")
        approver = UserFactory(office_approver=True)
        can, reason = svc.can_user_approve(pr, approver)
        assert can is True
        assert "may approve" in reason.lower()

    def test_wrong_first_stage_approver_is_rejected_for_lane(self):
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="office")
        approver = UserFactory(project_approver=True)
        can, reason = svc.can_user_approve(pr, approver)
        assert can is False
        assert "office approver" in reason.lower()

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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        svc.submit_for_approval(pr)
        history = svc.get_approval_history(pr)
        assert history.exists()

    def test_does_not_return_other_objects_logs(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
