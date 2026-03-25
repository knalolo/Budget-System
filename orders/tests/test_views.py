"""View tests for the purchase request HTML workflow."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from orders.models import PurchaseRequest


def _purchase_request_payload(project, category, *, action="draft") -> dict:
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Bench power supply",
        "vendor": "Acme Components",
        "currency": "SGD",
        "total_price": "450.00",
        "justification": "Needed for prototype validation.",
        "po_required": "False",
        "target_payment": "Jan 2026",
        "action": action,
    }


@pytest.mark.django_db
class TestPurchaseRequestCreateView:
    def test_create_saves_uploaded_quotation(
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
            "quotation.pdf",
            b"%PDF-1.4 quotation content",
            content_type="application/pdf",
        )
        payload = _purchase_request_payload(sample_project, sample_expense_category)
        payload["attachment_file_type"] = "quotation"
        payload["attachment_files"] = [upload]

        response = client.post(
            reverse("orders:purchase-request-create"),
            data=payload,
        )

        assert response.status_code == 302
        purchase_request = PurchaseRequest.objects.get(requester=regular_user)
        attachment = purchase_request.attachments.get()
        assert purchase_request.status == "draft"
        assert attachment.file_type == "quotation"
        assert attachment.original_filename == "quotation.pdf"

    def test_create_submit_saves_new_order_list_and_submits(
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
            "new-order-list.xlsx",
            b"PK\x03\x04 worksheet bytes",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        payload = _purchase_request_payload(
            sample_project,
            sample_expense_category,
            action="submit",
        )
        payload["attachment_file_type"] = "new_order_list"
        payload["attachment_files"] = [upload]

        response = client.post(
            reverse("orders:purchase-request-create"),
            data=payload,
        )

        assert response.status_code == 302
        purchase_request = PurchaseRequest.objects.get(requester=regular_user)
        attachment = purchase_request.attachments.get()
        assert purchase_request.status == "pending_pcm"
        assert attachment.file_type == "new_order_list"


@pytest.mark.django_db
class TestPurchaseRequestUploadView:
    def test_upload_endpoint_accepts_new_order_list_type(
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

        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Oscilloscope",
            vendor="Tek Supplier",
            currency="SGD",
            total_price="100.00",
            justification="Lab usage",
            po_required=False,
            target_payment="30 days",
            status="draft",
        )

        upload = SimpleUploadedFile(
            "new-order-list.xlsx",
            b"PK\x03\x04 worksheet bytes",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = client.post(
            reverse("orders:purchase-request-upload", args=[purchase_request.pk]),
            data={
                "file": upload,
                "file_type": "new_order_list",
            },
        )

        assert response.status_code == 200
        attachment = purchase_request.attachments.get()
        assert attachment.file_type == "new_order_list"

    def test_upload_endpoint_rejects_invalid_attachment_type(
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

        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Oscilloscope",
            vendor="Tek Supplier",
            currency="SGD",
            total_price="100.00",
            justification="Lab usage",
            po_required=False,
            target_payment="30 days",
            status="draft",
        )

        upload = SimpleUploadedFile(
            "quotation.pdf",
            b"%PDF-1.4 quotation content",
            content_type="application/pdf",
        )

        response = client.post(
            reverse("orders:purchase-request-upload", args=[purchase_request.pk]),
            data={
                "file": upload,
                "file_type": "invoice",
            },
        )

        assert response.status_code == 400
        assert not purchase_request.attachments.exists()


@pytest.mark.django_db
class TestPurchaseRequestOrderWorkflowView:
    def test_mark_ordered_redirects_to_payment_release_create_for_non_po_request(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Bench power supply",
            vendor="Acme Components",
            currency="SGD",
            total_price="450.00",
            justification="Needed for prototype validation.",
            po_required=False,
            target_payment="Jan 2026",
            status="approved",
        )

        response = client.post(
            reverse("orders:purchase-request-mark-ordered", args=[purchase_request.pk]),
        )

        assert response.status_code == 302
        assert response.url == f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"

    def test_po_required_request_must_be_marked_po_sent_before_ordered(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Bench power supply",
            vendor="Acme Components",
            currency="SGD",
            total_price="1450.00",
            justification="Needed for prototype validation.",
            po_required=True,
            target_payment="Jan 2026",
            status="approved",
        )

        response = client.post(
            reverse("orders:purchase-request-mark-ordered", args=[purchase_request.pk]),
        )

        assert response.status_code == 302
        assert response.url == reverse("orders:purchase-request-detail", args=[purchase_request.pk])

        purchase_request.refresh_from_db()
        assert purchase_request.status == "approved"
