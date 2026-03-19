"""Unit tests for payments.services (PaymentRelease workflow)."""
import pytest
from django.core.exceptions import ValidationError

from orders.tests.factories import UserFactory
from payments.services import (
    approve_payment_release,
    reject_payment_release,
    submit_payment_release,
)
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestSubmitPaymentRelease:
    def test_submit_draft_transitions_to_pending_pcm(self):
        pr = PaymentReleaseFactory(status="draft")
        updated = submit_payment_release(pr)
        assert updated.status == "pending_pcm"

    def test_submit_non_draft_raises(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        with pytest.raises(ValidationError):
            submit_payment_release(pr)

    def test_submission_creates_approval_log(self):
        from approvals.models import ApprovalLog

        pr = PaymentReleaseFactory(status="draft")
        updated = submit_payment_release(pr)
        assert ApprovalLog.objects.filter(object_id=updated.pk, action="submitted").exists()


@pytest.mark.django_db
class TestApprovePaymentRelease:
    def test_pcm_approval_transitions_to_pending_final(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        approver = UserFactory()
        updated = approve_payment_release(pr, approver)
        assert updated.status == "pending_final"
        assert updated.pcm_approver == approver
        assert updated.pcm_decision == "approved"

    def test_final_approval_transitions_to_approved(self):
        pr = PaymentReleaseFactory(status="pending_final")
        approver = UserFactory()
        updated = approve_payment_release(pr, approver)
        assert updated.status == "approved"
        assert updated.final_decision == "approved"

    def test_approval_with_comment(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        approver = UserFactory()
        updated = approve_payment_release(pr, approver, comment="Invoice verified")
        assert updated.pcm_comment == "Invoice verified"


@pytest.mark.django_db
class TestRejectPaymentRelease:
    def test_pcm_rejection(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        approver = UserFactory()
        updated = reject_payment_release(pr, approver, comment="Missing docs")
        assert updated.status == "rejected"
        assert updated.pcm_decision == "rejected"
        assert updated.pcm_comment == "Missing docs"

    def test_final_rejection(self):
        pr = PaymentReleaseFactory(status="pending_final")
        approver = UserFactory()
        updated = reject_payment_release(pr, approver)
        assert updated.status == "rejected"
        assert updated.final_decision == "rejected"
