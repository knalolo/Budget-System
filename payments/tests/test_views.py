"""View tests for the payment release HTML workflow."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import PurchaseRequestFactory
from payments.models import PaymentRelease
from payments.tests.factories import PaymentReleaseFactory


def _payment_release_payload(project, category, *, action="draft") -> dict:
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Advance payment for testing services",
        "vendor": "Playtest Vendor",
        "currency": "SGD",
        "payment_type": "standard",
        "payment_quantity": "1",
        "total_price": "500.00",
        "justification": "Needed to lock the test slot.",
        "po_number": "N/A",
        "target_payment": "2026-04-15",
        "action": action,
    }


@pytest.mark.django_db
class TestPaymentReleaseCreateView:
    def test_get_prefills_from_linked_purchase_request(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            ordered_quantity=2,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_required=False,
            target_payment="2026-04-15",
            status="ordered",
        )

        response = client.get(
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
        )

        assert response.status_code == 200
        assert response.context["source_purchase_request"] == purchase_request
        assert response.context["form"].initial["vendor"] == purchase_request.vendor
        assert response.context["form"].initial["po_number"] == "N/A"
        assert response.context["form"].initial["payment_quantity"] == 1

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

    def test_create_links_payment_to_purchase_request(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            ordered_quantity=1,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_required=False,
            target_payment="2026-04-15",
            status="ordered",
        )

        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["purchase_request"] = purchase_request.pk

        response = client.post(reverse("payments:create"), data=payload)

        assert response.status_code == 302
        payment = PaymentRelease.objects.get(requester=regular_user)
        assert payment.purchase_request == purchase_request
        assert payment.request_number == purchase_request.request_number.replace(
            "PR-",
            "RP-",
            1,
        )

    def test_create_syncs_request_number_with_linked_purchase_request(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            request_number="PR-20260325-0002",
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            ordered_quantity=1,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_required=False,
            target_payment="2026-04-15",
            status="ordered",
        )

        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["purchase_request"] = purchase_request.pk

        response = client.post(reverse("payments:create"), data=payload)

        assert response.status_code == 302
        payment = PaymentRelease.objects.get(requester=regular_user)
        assert payment.request_number == "RP-20260325-0002"

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

    def test_standard_payment_submit_requires_delivery_first(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            ordered_quantity=5,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_required=False,
            target_payment="2026-04-15",
            status="ordered",
        )

        payload = _payment_release_payload(
            sample_project,
            sample_expense_category,
            action="submit",
        )
        payload["purchase_request"] = purchase_request.pk

        response = client.post(reverse("payments:create"), data=payload, follow=True)

        assert response.status_code == 200
        payment = PaymentRelease.objects.get(requester=regular_user)
        assert payment.status == "draft"
        messages = [message.message for message in response.context["messages"]]
        assert any("goods recieve record first" in message for message in messages)

    def test_standard_payment_submit_rejects_when_full_advance_payment_already_covers_total(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            ordered_quantity=5,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_required=False,
            target_payment="2026-04-15",
            status="ordered",
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=5,
            status="fully_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            total_price=purchase_request.total_price,
        )
        PaymentRelease.objects.create(
            requester=regular_user,
            purchase_request=purchase_request,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Advance payment for testing services",
            vendor="Playtest Vendor",
            currency="SGD",
            payment_type="advance",
            payment_quantity=5,
            total_price="500.00",
            justification="Needed to lock the test slot.",
            po_number="N/A",
            target_payment="2026-04-15",
            status="approved",
        )

        payload = _payment_release_payload(
            sample_project,
            sample_expense_category,
            action="submit",
        )
        payload["purchase_request"] = purchase_request.pk
        payload["payment_quantity"] = "5"
        payload["total_price"] = "500.00"

        response = client.post(reverse("payments:create"), data=payload, follow=True)

        assert response.status_code == 200
        draft_payment = PaymentRelease.objects.filter(
            requester=regular_user,
            status="draft",
        ).latest("created_at")
        assert draft_payment.status == "draft"
        messages = [message.message for message in response.context["messages"]]
        assert any("already been fully covered" in message for message in messages)


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


@pytest.mark.django_db
class TestPaymentReleaseVisualCues:
    def test_payment_list_shows_advance_without_goods_recieve_badge(
        self,
        client,
        pcm_approver,
    ):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=20,
        )
        PaymentReleaseFactory(
            requester=purchase_request.requester,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=20,
            status="pending_pcm",
            vendor=purchase_request.vendor,
        )
        client.force_login(pcm_approver)

        response = client.get(reverse("payments:list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Advance Payment" in content
        assert "Advance Payment • No Goods recieve" in content
        assert "Supplier asked for prepayment" in content

    def test_payment_detail_shows_goods_recieve_backed_message_for_standard_payment(
        self,
        client,
        pcm_approver,
    ):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=10,
        )
        DeliverySubmissionFactory(
            requester=purchase_request.requester,
            purchase_request=purchase_request,
            delivered_quantity=10,
            status="fully_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            total_price=purchase_request.total_price,
        )
        payment = PaymentReleaseFactory(
            requester=purchase_request.requester,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="standard",
            payment_quantity=10,
            status="pending_pcm",
            vendor=purchase_request.vendor,
            total_price=purchase_request.total_price,
        )
        client.force_login(pcm_approver)

        response = client.get(reverse("payments:detail", args=[payment.pk]))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Goods recieved" in content
        assert "This payment is backed by delivered goods." in content
