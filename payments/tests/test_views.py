"""View tests for the payment release HTML workflow."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from payments.models import PaymentRelease


def _payment_release_payload(project, category, *, action="draft") -> dict:
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Advance payment for testing services",
        "vendor": "Playtest Vendor",
        "currency": "SGD",
        "total_price": "500.00",
        "justification": "Needed to lock the test slot.",
        "po_number": "N/A",
        "target_payment": "Apr 2026",
        "action": action,
    }


@pytest.mark.django_db
class TestPaymentReleaseCreateView:
    def test_create_saves_uploaded_invoice(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        settings,
        tmp_path,
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(regular_user)

        upload = SimpleUploadedFile(
            "official-invoice.pdf",
            b"%PDF-1.4 official invoice",
            content_type="application/pdf",
        )
        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["attachment_file_type"] = "invoice"
        payload["attachment_files"] = [upload]

        response = client.post(reverse("payments:create"), data=payload)

        assert response.status_code == 302
        payment = PaymentRelease.objects.get(requester=regular_user)
        attachment = payment.attachments.get()
        assert payment.status == "draft"
        assert attachment.file_type == "invoice"
        assert attachment.original_filename == "official-invoice.pdf"

    def test_create_submit_saves_proforma_and_submits(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        settings,
        tmp_path,
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(regular_user)

        upload = SimpleUploadedFile(
            "proforma-invoice.pdf",
            b"%PDF-1.4 proforma invoice",
            content_type="application/pdf",
        )
        payload = _payment_release_payload(
            sample_project,
            sample_expense_category,
            action="submit",
        )
        payload["attachment_file_type"] = "proforma_invoice"
        payload["attachment_files"] = [upload]

        response = client.post(reverse("payments:create"), data=payload)

        assert response.status_code == 302
        payment = PaymentRelease.objects.get(requester=regular_user)
        attachment = payment.attachments.get()
        assert payment.status == "pending_pcm"
        assert attachment.file_type == "proforma_invoice"


@pytest.mark.django_db
class TestPaymentReleaseUploadView:
    def test_upload_endpoint_accepts_proforma_invoice_type(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        settings,
        tmp_path,
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(regular_user)

        payment = PaymentRelease.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Testing service payment",
            vendor="Test Vendor",
            currency="SGD",
            total_price="100.00",
            justification="Validation",
            po_number="N/A",
            target_payment="30 days",
            status="draft",
        )

        upload = SimpleUploadedFile(
            "proforma-invoice.pdf",
            b"%PDF-1.4 proforma invoice",
            content_type="application/pdf",
        )

        response = client.post(
            reverse("payments:upload", args=[payment.pk]),
            data={
                "file": upload,
                "file_type": "proforma_invoice",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        attachment = payment.attachments.get()
        assert attachment.file_type == "proforma_invoice"

    def test_upload_endpoint_rejects_po_document_type(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        settings,
        tmp_path,
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(regular_user)

        payment = PaymentRelease.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Testing service payment",
            vendor="Test Vendor",
            currency="SGD",
            total_price="100.00",
            justification="Validation",
            po_number="N/A",
            target_payment="30 days",
            status="draft",
        )

        upload = SimpleUploadedFile(
            "po-document.pdf",
            b"%PDF-1.4 po document",
            content_type="application/pdf",
        )

        response = client.post(
            reverse("payments:upload", args=[payment.pk]),
            data={
                "file": upload,
                "file_type": "po_document",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert not payment.attachments.exists()
