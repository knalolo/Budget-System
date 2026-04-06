"""Unit tests for payments.services (PaymentRelease workflow)."""
import pytest
from django.core.exceptions import ValidationError

from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import PurchaseRequestFactory, UserFactory
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

    def test_standard_payment_requires_delivery(self):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=5,
            total_price=500,
        )
        payment_release = PaymentReleaseFactory(
            status="draft",
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=5,
            total_price=500,
        )

        with pytest.raises(ValidationError):
            submit_payment_release(payment_release)

    def test_standard_payment_respects_delivered_quantity_limit(self):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=10,
            total_price=1000,
        )
        DeliverySubmissionFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            delivered_quantity=4,
            total_price=400,
            status="partially_delivered",
        )
        payment_release = PaymentReleaseFactory(
            status="draft",
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=5,
            total_price=500,
        )

        with pytest.raises(ValidationError):
            submit_payment_release(payment_release)

    def test_advance_payment_can_submit_before_delivery(self):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=10,
            total_price=1000,
        )
        payment_release = PaymentReleaseFactory(
            status="draft",
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=10,
            total_price=1000,
        )

        updated = submit_payment_release(payment_release)
        assert updated.status == "pending_pcm"


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
