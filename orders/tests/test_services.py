"""Unit tests for orders.services (PurchaseRequest workflow)."""
import pytest
from django.core.exceptions import ValidationError
from unittest.mock import patch

from core.models import SystemConfig
from orders.services import (
    approve_purchase_request,
    check_po_threshold,
    mark_ordered,
    mark_po_sent,
    reject_purchase_request,
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
        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        assert updated.status == "pending_pcm"

    def test_submit_non_draft_raises(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        with pytest.raises(ValidationError):
            submit_purchase_request(pr)

    def test_submit_updates_po_required_when_above_threshold(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        pr = PurchaseRequestFactory(currency="SGD", total_price=2000, po_required=False)
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        assert updated.po_required is True

    def test_submit_creates_approval_log(self):
        from approvals.models import ApprovalLog

        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission"):
            updated = submit_purchase_request(pr)
        logs = ApprovalLog.objects.filter(object_id=updated.pk)
        assert logs.exists()
        assert logs.first().action == "submitted"

    def test_submit_notification_failure_does_not_raise(self):
        """Email notification failures must not bubble up."""
        pr = PurchaseRequestFactory(status="draft")
        with patch("orders.services.notify_submission", side_effect=Exception("SMTP down")):
            updated = submit_purchase_request(pr)
        assert updated.status == "pending_pcm"


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


# ---------------------------------------------------------------------------
# mark_po_sent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMarkPoSent:
    def test_approved_transitions_to_po_sent(self):
        pr = PurchaseRequestFactory(status="approved")
        updated = mark_po_sent(pr)
        assert updated.status == "po_sent"

    def test_non_approved_raises(self):
        pr = PurchaseRequestFactory(status="draft")
        with pytest.raises(ValidationError):
            mark_po_sent(pr)

    def test_creates_status_log(self):
        from approvals.models import ApprovalLog

        pr = PurchaseRequestFactory(status="approved")
        updated = mark_po_sent(pr)
        log = ApprovalLog.objects.filter(object_id=updated.pk, new_status="po_sent").first()
        assert log is not None
        assert log.action == "status_changed"


# ---------------------------------------------------------------------------
# mark_ordered
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMarkOrdered:
    def test_approved_transitions_to_ordered(self):
        pr = PurchaseRequestFactory(status="approved")
        updated = mark_ordered(pr)
        assert updated.status == "ordered"

    def test_po_required_approved_raises_until_po_sent(self):
        pr = PurchaseRequestFactory(status="approved", po_required=True)
        with pytest.raises(ValidationError):
            mark_ordered(pr)

    def test_po_sent_transitions_to_ordered(self):
        pr = PurchaseRequestFactory(status="po_sent")
        updated = mark_ordered(pr)
        assert updated.status == "ordered"

    def test_invalid_status_raises(self):
        pr = PurchaseRequestFactory(status="draft")
        with pytest.raises(ValidationError):
            mark_ordered(pr)

    def test_creates_status_log(self):
        from approvals.models import ApprovalLog

        pr = PurchaseRequestFactory(status="approved")
        updated = mark_ordered(pr)
        log = ApprovalLog.objects.filter(object_id=updated.pk, new_status="ordered").first()
        assert log is not None
