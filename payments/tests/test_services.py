"""Unit tests for payments.services (PaymentRelease workflow)."""
from decimal import Decimal

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

    def test_submit_rejected_payment_resets_current_decisions_and_keeps_number(self):
        from approvals.models import ApprovalLog

        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        approver = UserFactory()
        payment = PaymentReleaseFactory(status="pending_pcm", payment_type="advance")
        rejected = reject_payment_release(payment, approver, comment="Missing docs")
        request_number = rejected.request_number
        rejection_log_count = ApprovalLog.objects.filter(object_id=rejected.pk).count()

        updated = submit_payment_release(rejected)

        assert updated.status == "pending_pcm"
        assert updated.request_number == request_number
        assert updated.pcm_approver is None
        assert updated.pcm_decision == "pending"
        assert updated.pcm_comment == ""
        assert updated.pcm_decided_at is None
        assert updated.final_approver is None
        assert updated.final_decision == "pending"
        assert ApprovalLog.objects.filter(object_id=updated.pk).count() == rejection_log_count + 1

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
            status="approved",
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
            status="approved",
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
            status="approved",
            execution_mode="payment_first",
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

    def test_second_advance_payment_is_limited_to_remaining_pr_balance(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="approved",
            execution_mode="payment_first",
            total_price=Decimal("1000.00"),
        )
        PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            total_price=Decimal("200.00"),
            status="approved",
        )
        second_payment = PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            total_price=Decimal("801.00"),
            status="draft",
        )

        with pytest.raises(ValidationError, match="remaining payable amount"):
            submit_payment_release(second_payment)

    def test_another_payment_cannot_submit_while_one_is_under_approval(self):
        purchase_request = PurchaseRequestFactory(
            status="approved",
            execution_mode="payment_first",
            total_price="1000.00",
        )
        PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            total_price="200.00",
            status="pending_pcm",
        )
        second_payment = PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            total_price="300.00",
            status="draft",
        )

        with pytest.raises(ValidationError, match="still under approval"):
            submit_payment_release(second_payment)

    def test_payment_first_request_can_pay_remaining_balance_after_delivery(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="approved",
            execution_mode="payment_first",
            ordered_quantity=1,
            total_price=Decimal("1000.00"),
        )
        PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=1,
            total_price=Decimal("200.00"),
            status="approved",
        )
        DeliverySubmissionFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            delivered_quantity=1,
            total_price=Decimal("1000.00"),
            status="fully_delivered",
        )
        final_payment = PaymentReleaseFactory(
            purchase_request=purchase_request,
            requester=purchase_request.requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=1,
            total_price=Decimal("800.00"),
            status="draft",
        )

        updated = submit_payment_release(final_payment)

        assert updated.status == "pending_pcm"

    def test_delivery_first_rejects_advance_payment_before_delivery(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="approved",
            execution_mode="delivery_first",
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

        with pytest.raises(ValidationError, match="goods receive first"):
            submit_payment_release(payment_release)

    def test_standard_payment_uses_delivered_line_item_value_cap(self):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        purchase_request = PurchaseRequestFactory(
            status="approved",
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
            status="approved",
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
        pr = PaymentReleaseFactory(
            status="pending_final",
            currency="SGD",
            total_price=321.45,
        )
        approver = UserFactory()
        updated = approve_payment_release(pr, approver)
        assert updated.status == "approved"
        assert updated.final_decision == "approved"
        assert updated.approved_amount_sgd == Decimal("321.45")
        assert updated.approval_fx_rate == Decimal("1")
        assert updated.approval_fx_date is not None

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
