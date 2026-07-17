"""Unit tests for orders.services (PurchaseRequest workflow)."""
import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from core.models import SystemConfig
from orders.services import (
    approve_purchase_request_cancellation,
    approve_purchase_request,
    check_po_threshold,
    reject_purchase_request_cancellation,
    reject_purchase_request,
    request_purchase_request_cancellation,
    submit_purchase_request,
)
from orders.tests.factories import PurchaseRequestFactory, UserFactory


# ---------------------------------------------------------------------------
# check_po_threshold
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckPoThreshold:
    def test_under_threshold_sgd(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        assert check_po_threshold("SGD", 999) is False

    def test_over_threshold_sgd(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        assert check_po_threshold("SGD", 1001) is True

    def test_exactly_at_threshold(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        assert check_po_threshold("SGD", 1000) is True

    def test_usd_threshold(self):
        SystemConfig.set_value("po_threshold_usd", 5000)
        assert check_po_threshold("USD", 6000) is True
        assert check_po_threshold("USD", 4999) is False

    def test_eur_threshold(self):
        SystemConfig.set_value("po_threshold_eur", 3000)
        assert check_po_threshold("EUR", 3000) is True

    def test_no_config_returns_false(self):
        SystemConfig.objects.filter(key="po_threshold_sgd").delete()
        assert check_po_threshold("SGD", 99999) is False

    def test_unknown_currency_returns_false(self):
        assert check_po_threshold("JPY", 99999) is False

    def test_case_insensitive_currency(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        assert check_po_threshold("sgd", 1500) is True


# ---------------------------------------------------------------------------
# submit_purchase_request
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitPurchaseRequest:
    def test_submit_draft_transitions_to_pending_pcm(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        assert updated.status == "pending_pcm"

    def test_submit_non_draft_raises(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        with pytest.raises(ValidationError):
            submit_purchase_request(pr)

    def test_submit_rejected_request_resets_current_decisions_and_keeps_number(self):
        from approvals.models import ApprovalLog

        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        approver = UserFactory()
        pr = PurchaseRequestFactory(status="pending_pcm")
        rejected = reject_purchase_request(pr, approver, comment="Too expensive")
        request_number = rejected.request_number
        rejection_log_count = ApprovalLog.objects.filter(object_id=rejected.pk).count()

        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(rejected)

        assert updated.status == "pending_pcm"
        assert updated.request_number == request_number
        assert updated.pcm_approver is None
        assert updated.pcm_decision == "pending"
        assert updated.pcm_comment == ""
        assert updated.pcm_decided_at is None
        assert updated.final_approver is None
        assert updated.final_decision == "pending"
        assert ApprovalLog.objects.filter(object_id=updated.pk).count() == rejection_log_count + 1

    def test_submit_updates_po_required_when_above_threshold(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(currency="SGD", total_price=2000, po_required=False)
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        assert updated.po_required is True

    def test_submit_creates_approval_log(self):
        from approvals.models import ApprovalLog

        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        logs = ApprovalLog.objects.filter(object_id=updated.pk)
        assert logs.exists()
        assert logs.first().action == "submitted"

    def test_submit_notification_failure_does_not_raise(self):
        """Email notification failures must not bubble up."""
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission", side_effect=Exception("SMTP down")):
            updated = submit_purchase_request(pr)
        assert updated.status == "pending_pcm"

    def test_submit_requires_matching_purchase_type_approver(self):
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(status="draft", purchase_type="office")

        with patch("orders.services.notify_submission"):
            with pytest.raises(ValidationError, match="Office Approver"):
                submit_purchase_request(pr)


@pytest.mark.django_db
class TestPurchaseRequestCancellation:
    def test_requester_can_request_cancellation_for_approved_pr(self):
        from approvals.models import ApprovalLog

        requester = UserFactory()
        pr = PurchaseRequestFactory(requester=requester, status="approved")

        updated = request_purchase_request_cancellation(pr, requester, "Quotation is wrong")

        assert updated.status == "cancellation_pending"
        assert updated.cancellation_requested_by == requester
        assert updated.cancellation_reason == "Quotation is wrong"
        assert updated.cancellation_decision == "pending"
        assert ApprovalLog.objects.filter(
            object_id=updated.pk,
            old_status="approved",
            new_status="cancellation_pending",
        ).exists()

    def test_requester_cannot_request_cancellation_for_non_approved_pr(self):
        requester = UserFactory()
        pr = PurchaseRequestFactory(requester=requester, status="pending_pcm")

        with pytest.raises(ValidationError, match="Only approved"):
            request_purchase_request_cancellation(pr, requester, "Wrong quote")

    def test_non_requester_cannot_request_cancellation(self):
        pr = PurchaseRequestFactory(status="approved")
        other_user = UserFactory()

        with pytest.raises(ValidationError, match="Only the requester"):
            request_purchase_request_cancellation(pr, other_user, "Wrong quote")

    def test_final_approver_can_approve_cancellation(self):
        requester = UserFactory()
        final = UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(requester=requester, status="approved")
        request_purchase_request_cancellation(pr, requester, "Wrong quote")

        updated = approve_purchase_request_cancellation(pr, final, "Agreed")

        assert updated.status == "cancelled"
        assert updated.cancellation_decision == "approved"
        assert updated.cancellation_decided_by == final
        assert updated.cancellation_decision_comment == "Agreed"

    def test_final_approver_can_reject_cancellation(self):
        requester = UserFactory()
        final = UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(requester=requester, status="approved")
        request_purchase_request_cancellation(pr, requester, "Wrong quote")

        updated = reject_purchase_request_cancellation(pr, final, "Keep original")

        assert updated.status == "approved"
        assert updated.cancellation_decision == "rejected"
        assert updated.cancellation_decided_by == final
        assert updated.cancellation_decision_comment == "Keep original"

    def test_regular_user_cannot_decide_cancellation(self):
        requester = UserFactory()
        regular = UserFactory()
        pr = PurchaseRequestFactory(requester=requester, status="approved")
        request_purchase_request_cancellation(pr, requester, "Wrong quote")

        with pytest.raises(ValidationError, match="Final Approver or Admin"):
            approve_purchase_request_cancellation(pr, regular, "No")


# ---------------------------------------------------------------------------
# approve_purchase_request
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApprovePurchaseRequest:
    def test_pcm_approval_transitions_to_pending_final(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        # approver must not be the requester
        updated = approve_purchase_request(pr, approver)
        assert updated.status == "pending_final"
        assert updated.pcm_approver == approver
        assert updated.pcm_decision == "approved"

    def test_final_approval_transitions_to_approved(self):
        pr = PurchaseRequestFactory(status="pending_final")
        approver = UserFactory()
        updated = approve_purchase_request(pr, approver)
        assert updated.status == "approved"
        assert updated.final_approver == approver
        assert updated.final_decision == "approved"

    def test_approval_comment_is_stored(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        updated = approve_purchase_request(pr, approver, comment="Looks good")
        assert updated.pcm_comment == "Looks good"


# ---------------------------------------------------------------------------
# reject_purchase_request
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRejectPurchaseRequest:
    def test_pcm_rejection_transitions_to_rejected(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        approver = UserFactory()
        updated = reject_purchase_request(pr, approver, comment="Too expensive")
        assert updated.status == "rejected"
        assert updated.pcm_decision == "rejected"
        assert updated.pcm_comment == "Too expensive"

    def test_final_rejection_transitions_to_rejected(self):
        pr = PurchaseRequestFactory(status="pending_final")
        approver = UserFactory()
        updated = reject_purchase_request(pr, approver)
        assert updated.status == "rejected"
        assert updated.final_decision == "rejected"


