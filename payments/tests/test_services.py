"""Unit tests for payments.services (PaymentRelease workflow)."""
import pytest
from django.core.exceptions import ValidationError

from deliveries.models import DeliverySubmissionLineItem
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.models import PurchaseRequestLineItem
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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PaymentReleaseFactory(status="draft")
        updated = submit_payment_release(pr)
        assert updated.status == "pending_pcm"

    def test_submit_non_draft_raises(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        with pytest.raises(ValidationError):
            submit_payment_release(pr)

    def test_submission_creates_approval_log(self):
        from approvals.models import ApprovalLog

        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PaymentReleaseFactory(status="draft")
        updated = submit_payment_release(pr)
        assert ApprovalLog.objects.filter(object_id=updated.pk, action="submitted").exists()

    def test_standard_payment_requires_delivery(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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

    def test_standard_payment_uses_delivered_line_item_value_cap(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=20,
            total_price=995,
            currency="SGD",
        )
        line_item_1 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="AAA",
            quantity=5,
            unit_price="100.00",
            total_price="500.00",
            currency="SGD",
        )
        line_item_2 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=2,
            product="BBB",
            quantity=15,
            unit_price="33.00",
            total_price="495.00",
            currency="SGD",
        )
        submission = DeliverySubmissionFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            delivered_quantity=19,
            total_price=962,
            status="partially_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=submission,
            purchase_request_line_item=line_item_1,
            sequence=1,
            product="AAA",
            ordered_quantity=5,
            delivered_quantity=5,
            unit_price="100.00",
            total_price="500.00",
            currency="SGD",
            status="fully_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=submission,
            purchase_request_line_item=line_item_2,
            sequence=2,
            product="BBB",
            ordered_quantity=15,
            delivered_quantity=14,
            unit_price="33.00",
            total_price="462.00",
            currency="SGD",
            status="partially_delivered",
        )
        payment_release = PaymentReleaseFactory(
            status="draft",
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=19,
            total_price=963,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
        )

        with pytest.raises(ValidationError, match="SGD 962.00"):
            submit_payment_release(payment_release)

    def test_submit_requires_matching_purchase_type_approver(self):
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            purchase_type="office",
            ordered_quantity=2,
            total_price=200,
        )
        DeliverySubmissionFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            delivered_quantity=2,
            total_price=200,
            status="fully_delivered",
        )
        payment_release = PaymentReleaseFactory(
            status="draft",
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=2,
            total_price=200,
        )

        with pytest.raises(ValidationError, match="Office Approver"):
            submit_payment_release(payment_release)


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
