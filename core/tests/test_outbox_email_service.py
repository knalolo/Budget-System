from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import EmailOutbox, FileAttachment, SystemConfig
from core.services.outbox_email_service import (
    queue_goods_followup_email,
    queue_payment_final_approved_email,
    queue_pr_final_approved_email,
    queue_pr_submitted_email,
    queue_workflow_completed_email,
)
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.services import approve_purchase_request, submit_purchase_request
from orders.tests.factories import PurchaseRequestFactory, UserFactory
from payments.services import approve_payment_release, submit_payment_release
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestOutlookEmailSafety:
    def test_disabled_switch_does_not_create_queue_item(self):
        approver = UserFactory(project_approver=True, email="approver@example.test")
        pr = PurchaseRequestFactory()

        queued = queue_pr_submitted_email(pr, event_key="disabled-test")

        assert approver.email
        assert queued is None
        assert EmailOutbox.objects.count() == 0


@pytest.mark.django_db
class TestOutboxWorkflowEmails:
    @pytest.fixture(autouse=True)
    def enable_outlook_queue(self, settings):
        settings.OUTLOOK_EMAIL_ENABLED = True
        settings.OUTLOOK_FROM_MAILBOX = "SGRDPR@WAGO.com"

    def setup_method(self):
        SystemConfig.set_value("notify_li_mei_email", "limei@wago.com")
        SystemConfig.set_value("notify_jolly_email", "jolly@wago.com")
        SystemConfig.set_value("notify_jess_email", "jess@wago.com")

    def test_pr_approval_flow_queues_each_business_event_once(self):
        requester = UserFactory(email="requester@example.test")
        first = UserFactory(project_approver=True, email="approver@example.test")
        final = UserFactory(final_approver=True, email="final@example.test")
        SystemConfig.set_value("po_threshold_sgd", 1000)
        pr = PurchaseRequestFactory(requester=requester, total_price=100)

        submit_purchase_request(pr)
        approve_purchase_request(pr, first, "Approved")
        approve_purchase_request(pr, final, "Final approved")

        assert list(EmailOutbox.objects.order_by("created_at").values_list("event_type", flat=True)) == [
            "pr_submitted",
            "pr_first_approved",
            "pr_final_approved",
        ]
        assert EmailOutbox.objects.get(event_type="pr_submitted").to_emails == first.email
        assert EmailOutbox.objects.get(event_type="pr_first_approved").to_emails == final.email

    def test_missing_requester_email_creates_failed_audit_item(self):
        requester = UserFactory(email="")
        pr = PurchaseRequestFactory(requester=requester, status="approved")

        queued = queue_pr_final_approved_email(pr, event_key="missing-requester-email")

        assert queued.status == EmailOutbox.STATUS_FAILED
        assert queued.to_emails == ""
        assert "No valid primary recipient" in queued.last_error

    def test_pr_final_approved_adds_jolly_and_quotation_when_po_is_required(self):
        requester = UserFactory(email="requester@example.test")
        SystemConfig.set_value("po_threshold_sgd", 100)
        pr = PurchaseRequestFactory(requester=requester, status="approved", total_price=500)
        attachment = _attach_file(pr, "quotation", "quotation.pdf", b"quotation")

        queued = queue_pr_final_approved_email(pr, event_key="pr-final-approved")

        assert queued.from_mailbox == "SGRDPR@WAGO.com"
        assert queued.to_emails == requester.email
        assert queued.cc_emails == "limei@wago.com;jolly@wago.com"
        assert queued.attachment_paths == [str(Path(attachment.file.path).resolve())]
        assert "PO Required: Yes" in queued.body_html
        assert "raise the Purchase Order" in queued.body_html
        assert "href=" not in queued.body_html
        assert "http://" not in queued.body_html
        assert "https://" not in queued.body_html

    def test_payment_final_approved_goes_to_li_mei_with_requester_cc_and_invoice(self):
        requester = UserFactory(email="requester@example.test")
        pr = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            planned_payment_count=3,
        )
        payment = PaymentReleaseFactory(
            requester=requester,
            purchase_request=pr,
            status="approved",
            payment_type="standard",
        )
        attachment = _attach_file(payment, "invoice", "invoice.pdf", b"invoice")

        queued = queue_payment_final_approved_email(payment, event_key="payment-final-approved")

        assert queued.to_emails == "limei@wago.com"
        assert queued.cc_emails == requester.email
        assert queued.attachment_paths == [str(Path(attachment.file.path).resolve())]
        assert pr.request_number in queued.body_html
        assert payment.request_number in queued.body_html
        assert "Payment 1 of 3" in queued.body_html
        assert "Progress Payment" in queued.body_html

    def test_advance_payment_flow_queues_approval_and_goods_followup_events(self):
        requester = UserFactory(email="requester@example.test")
        first = UserFactory(project_approver=True, email="approver@example.test")
        final = UserFactory(final_approver=True, email="final@example.test")
        pr = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            execution_mode="payment_first",
            ordered_quantity=1,
            total_price=100,
        )
        payment = PaymentReleaseFactory(
            requester=requester,
            purchase_request=pr,
            project=pr.project,
            expense_category=pr.expense_category,
            status="draft",
            payment_type="advance",
            payment_quantity=1,
            total_price=100,
        )

        submit_payment_release(payment)
        approve_payment_release(payment, first, "Approved")
        approve_payment_release(payment, final, "Final approved")

        assert set(EmailOutbox.objects.values_list("event_type", flat=True)) == {
            "payment_submitted",
            "payment_first_approved",
            "payment_final_approved",
            "advance_payment_goods_followup",
        }
        followup = EmailOutbox.objects.get(event_type="advance_payment_goods_followup")
        assert followup.to_emails == requester.email
        assert "Goods Receive is not complete" in followup.body_html

    def test_partial_goods_receive_emails_requester_and_ccs_jess(self):
        requester = UserFactory(email="requester@example.test")
        pr = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=10,
            total_price=1000,
        )
        delivery = DeliverySubmissionFactory(
            requester=requester,
            purchase_request=pr,
            delivered_quantity=4,
            total_price=400,
            status="partially_delivered",
        )

        queued = queue_goods_followup_email(delivery, event_key="goods-partial")

        assert queued.to_emails == requester.email
        assert queued.cc_emails == "jess@wago.com"
        assert "not been fully received" in queued.body_html
        assert "same Goods Receive record" in queued.body_html

    def test_completed_workflow_is_idempotent(self):
        requester = UserFactory(email="requester@example.test")
        pr = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=1,
            total_price=100,
        )
        DeliverySubmissionFactory(
            requester=requester,
            purchase_request=pr,
            delivered_quantity=1,
            total_price=100,
            status="fully_delivered",
        )
        PaymentReleaseFactory(
            requester=requester,
            purchase_request=pr,
            payment_quantity=1,
            total_price=100,
            status="approved",
        )

        first = queue_workflow_completed_email(pr)
        second = queue_workflow_completed_email(pr)

        assert first is not None
        assert second.pk == first.pk
        assert EmailOutbox.objects.filter(event_type="workflow_completed").count() == 1


def _attach_file(obj, file_type: str, filename: str, content: bytes) -> FileAttachment:
    return FileAttachment.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        file=SimpleUploadedFile(filename, content, content_type="application/pdf"),
        original_filename=filename,
        file_type=file_type,
        file_size=len(content),
        uploaded_by=obj.requester,
    )
