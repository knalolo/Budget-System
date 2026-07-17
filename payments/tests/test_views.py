"""View tests for the payment release HTML workflow."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from deliveries.models import DeliverySubmissionLineItem
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.models import PurchaseRequestLineItem
from orders.tests.factories import PurchaseRequestFactory, UserFactory
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
    def test_pcm_approver_cannot_open_create_page(self, client, pcm_approver):
        client.force_login(pcm_approver)

        response = client.get(reverse("payments:create"))

        assert response.status_code == 403

    def test_requester_cannot_view_another_users_payment_detail(self, client, regular_user):
        other_user = UserFactory()
        payment = PaymentReleaseFactory(requester=other_user)
        client.force_login(regular_user)

        response = client.get(reverse("payments:detail", args=[payment.pk]))

        assert response.status_code == 403

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
        assert response.context["form"].initial["payment_type"] == "advance"
        assert response.context["form"].initial["payment_quantity"] == 2

    def test_get_linked_purchase_request_reopens_existing_draft(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="approved",
        )
        draft = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            expense_category=sample_expense_category,
            project=sample_project,
            status="draft",
        )
        client.force_login(regular_user)

        response = client.get(
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
        )

        assert response.status_code == 302
        assert response.url == reverse("payments:update", args=[draft.pk])

    def test_get_linked_purchase_request_reopens_existing_active_payment(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="approved",
        )
        payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            expense_category=sample_expense_category,
            project=sample_project,
            status="pending_pcm",
        )
        client.force_login(regular_user)

        response = client.get(
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
        )

        assert response.status_code == 302
        assert response.url == reverse("payments:detail", args=[payment.pk])

    def test_get_prefills_standard_payment_from_delivered_line_item_value(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="ordered",
            ordered_quantity=20,
            total_price=995,
            currency="SGD",
            vendor="Coway",
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
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=19,
            total_price=962,
            status="partially_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
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

        response = client.get(
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
        )

        assert response.status_code == 200
        assert response.context["form"].initial["payment_quantity"] == 19
        assert str(response.context["form"].initial["total_price"]) == "962.00"
        assert (
            str(response.context["source_purchase_request_summary"]["max_standard_payment_total"])
            == "962.00"
        )

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

    def test_duplicate_create_token_does_not_create_second_payment_release(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        client.force_login(regular_user)
        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["create_token"] = "same-payment-submit-token"

        first_response = client.post(reverse("payments:create"), data=payload)
        second_response = client.post(reverse("payments:create"), data=payload)

        assert first_response.status_code == 302
        assert second_response.status_code == 302
        assert PaymentRelease.objects.filter(requester=regular_user).count() == 1

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

    def test_create_reuses_existing_linked_draft(
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
            status="approved",
        )
        draft = PaymentRelease.objects.create(
            requester=regular_user,
            purchase_request=purchase_request,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Old draft",
            vendor="Old Vendor",
            currency="SGD",
            payment_type="standard",
            payment_quantity=1,
            total_price="100.00",
            justification="Old reason",
            po_number="N/A",
            target_payment="2026-04-15",
            status="draft",
        )

        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["purchase_request"] = purchase_request.pk

        response = client.post(reverse("payments:create"), data=payload)

        assert response.status_code == 302
        assert PaymentRelease.objects.filter(purchase_request=purchase_request).count() == 1
        draft.refresh_from_db()
        assert draft.vendor == purchase_request.vendor
        assert draft.payment_type == "advance"
        assert draft.payment_quantity == purchase_request.ordered_quantity

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
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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

    def test_no_goods_payment_submit_is_treated_as_advance_payment(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
        assert payment.payment_type == "advance"
        assert payment.payment_quantity == purchase_request.ordered_quantity
        assert payment.status == "pending_pcm"
        messages = [message.message for message in response.context["messages"]]
        assert not any("goods recieve record first" in message for message in messages)

    def test_existing_no_goods_standard_draft_submits_as_advance_payment(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
            status="approved",
        )
        payment = PaymentRelease.objects.create(
            requester=regular_user,
            purchase_request=purchase_request,
            expense_category=sample_expense_category,
            project=sample_project,
            description=purchase_request.description,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            payment_type="standard",
            payment_quantity=1,
            total_price="500.00",
            justification=purchase_request.justification,
            po_number="N/A",
            target_payment="2026-04-15",
            status="draft",
        )

        response = client.post(reverse("payments:submit", args=[payment.pk]), follow=True)

        assert response.status_code == 200
        payment.refresh_from_db()
        assert payment.payment_type == "advance"
        assert payment.payment_quantity == purchase_request.ordered_quantity
        assert payment.status == "pending_pcm"

    def test_create_redirects_when_existing_active_payment_already_covers_total(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from orders.models import PurchaseRequest

        client.force_login(regular_user)
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
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
        active_payment = PaymentRelease.objects.create(
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
        assert not PaymentRelease.objects.filter(
            requester=regular_user,
            status="draft",
        ).exists()
        assert PaymentRelease.objects.filter(purchase_request=purchase_request).count() == 1
        assert response.resolver_match.view_name == "payments:detail"
        assert response.context["payment"] == active_payment


@pytest.mark.django_db
class TestPaymentReleaseRejectedEdit:
    def test_requester_can_edit_rejected_payment_back_to_draft(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        from approvals.models import ApprovalLog

        payment = PaymentReleaseFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="rejected",
            pcm_decision="rejected",
            pcm_comment="Missing docs",
        )
        request_number = payment.request_number
        client.force_login(regular_user)
        payload = _payment_release_payload(sample_project, sample_expense_category)
        payload["vendor"] = "Updated Payment Vendor"

        response = client.post(reverse("payments:update", args=[payment.pk]), data=payload)

        assert response.status_code == 302
        payment.refresh_from_db()
        assert payment.request_number == request_number
        assert payment.status == "draft"
        assert payment.vendor == "Updated Payment Vendor"
        assert payment.pcm_decision == "pending"
        assert payment.pcm_comment == ""
        assert ApprovalLog.objects.filter(object_id=payment.pk, action="status_changed").exists()

    def test_rejected_payment_edit_page_shows_attachment_controls(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        settings,
        tmp_path,
    ):
        settings.MEDIA_ROOT = tmp_path
        payment = PaymentReleaseFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="rejected",
        )
        client.force_login(regular_user)
        upload = SimpleUploadedFile(
            "old-invoice.pdf",
            b"%PDF-1.4 old invoice",
            content_type="application/pdf",
        )
        client.post(
            reverse("payments:upload", args=[payment.pk]),
            data={"file": upload, "file_type": "invoice"},
        )

        response = client.get(reverse("payments:update", args=[payment.pk]))

        assert response.status_code == 200
        assert b"old-invoice.pdf" in response.content
        assert b"Delete" in response.content
        assert b"Upload File" in response.content

    def test_rejected_payment_edit_page_places_attachments_before_submit_actions(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        payment = PaymentReleaseFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="rejected",
        )
        client.force_login(regular_user)

        response = client.get(reverse("payments:update", args=[payment.pk]))
        content = response.content.decode()

        assert response.status_code == 200
        assert content.index("Attachments") < content.index("Save &amp; Submit for Approval")


@pytest.mark.django_db
class TestPaymentReleaseDeleteView:
    def test_admin_detail_page_labels_delete_as_workflow_delete(
        self,
        client,
        admin_user,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        payment = PaymentReleaseFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="approved",
        )
        client.force_login(admin_user)

        response = client.get(reverse("payments:detail", args=[payment.pk]))

        assert response.status_code == 200
        assert b"Delete Workflow" in response.content
        assert b"Delete Draft" not in response.content


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

    def test_rejected_payment_attachment_can_be_deleted(
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
            description="Testing rejected payment",
            vendor="Test Vendor",
            currency="SGD",
            total_price="100.00",
            justification="Validation",
            po_number="N/A",
            target_payment="30 days",
            status="rejected",
        )
        upload = SimpleUploadedFile(
            "old-invoice.pdf",
            b"%PDF-1.4 old invoice",
            content_type="application/pdf",
        )
        client.post(
            reverse("payments:upload", args=[payment.pk]),
            data={"file": upload, "file_type": "invoice"},
        )
        attachment = payment.attachments.get()
        stored_file_name = attachment.file.name

        response = client.post(
            reverse("payments:delete-attachment", args=[payment.pk, attachment.pk]),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert not payment.attachments.exists()
        assert not attachment.file.storage.exists(stored_file_name)

    def test_pending_payment_attachment_cannot_be_deleted(
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
            description="Testing pending payment",
            vendor="Test Vendor",
            currency="SGD",
            total_price="100.00",
            justification="Validation",
            po_number="N/A",
            target_payment="30 days",
            status="draft",
        )
        upload = SimpleUploadedFile(
            "submitted-invoice.pdf",
            b"%PDF-1.4 submitted invoice",
            content_type="application/pdf",
        )
        client.post(
            reverse("payments:upload", args=[payment.pk]),
            data={"file": upload, "file_type": "invoice"},
        )
        attachment = payment.attachments.get()
        payment.status = "pending_pcm"
        payment.save(update_fields=["status"])

        response = client.post(
            reverse("payments:delete-attachment", args=[payment.pk, attachment.pk]),
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 403
        assert payment.attachments.filter(pk=attachment.pk).exists()


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
        assert "This payment is backed by cumulative delivered line-item value." in content
