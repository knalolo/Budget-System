"""View tests for the purchase request HTML workflow."""

import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from deliveries.models import DeliverySubmission, DeliverySubmissionLineItem
from orders.models import PurchaseRequest
from orders.models import PurchaseRequestLineItem
from payments.models import PaymentRelease


def _purchase_request_payload(project, category, *, action="draft") -> dict:
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Bench power supply",
        "vendor": "Acme Components",
        "currency": "SGD",
        "ordered_quantity": "2",
        "total_price": "450.00",
        "justification": "Needed for prototype validation.",
        "po_required": "False",
        "target_payment": "2026-01-15",
        "action": action,
    }


@pytest.mark.django_db
class TestPurchaseRequestCreateView:
    def test_pcm_approver_cannot_open_create_page(self, client, pcm_approver):
        client.force_login(pcm_approver)

        response = client.get(reverse("orders:purchase-request-create"))

        assert response.status_code == 403

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

    def test_create_with_multiple_line_items_aggregates_totals_and_saves_rows(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        client.force_login(regular_user)

        payload = {
            "expense_category": sample_expense_category.pk,
            "project": sample_project.pk,
            "vendor": "Acme Components",
            "justification": "Needed for prototype validation.",
            "po_required": "False",
            "target_payment": "2026-01-15",
            "action": "draft",
            "line_items_json": json.dumps(
                [
                    {
                        "sequence": 1,
                        "product": "Sensor head",
                        "quantity": 2,
                        "unit_price": "100.00",
                        "currency": "SGD",
                    },
                    {
                        "sequence": 2,
                        "product": "Control board",
                        "quantity": 3,
                        "unit_price": "50.00",
                        "currency": "SGD",
                    },
                ]
            ),
        }

        response = client.post(
            reverse("orders:purchase-request-create"),
            data=payload,
        )

        assert response.status_code == 302
        purchase_request = PurchaseRequest.objects.get(requester=regular_user)
        assert purchase_request.ordered_quantity == 5
        assert str(purchase_request.total_price) == "350.00"
        assert purchase_request.currency == "SGD"
        assert purchase_request.line_items.count() == 2


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
            ordered_quantity=1,
            total_price="100.00",
            justification="Lab usage",
            po_required=False,
            target_payment="2026-01-15",
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
            ordered_quantity=1,
            total_price="100.00",
            justification="Lab usage",
            po_required=False,
            target_payment="2026-01-15",
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
    def test_mark_ordered_redirects_to_delivery_create_for_non_po_request(
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
            ordered_quantity=2,
            total_price="450.00",
            justification="Needed for prototype validation.",
            po_required=False,
            target_payment="2026-01-15",
            status="approved",
        )

        response = client.post(
            reverse("orders:purchase-request-mark-ordered", args=[purchase_request.pk]),
        )

        assert response.status_code == 302
        assert response.url == f"{reverse('deliveries:create')}?purchase_request={purchase_request.pk}"

    def test_po_required_request_mark_ordered_now_redirects_to_goods_receive_without_mutating_pr(
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
            ordered_quantity=2,
            total_price="1450.00",
            justification="Needed for prototype validation.",
            po_required=True,
            target_payment="2026-01-15",
            status="approved",
        )

        response = client.post(
            reverse("orders:purchase-request-mark-ordered", args=[purchase_request.pk]),
        )

        assert response.status_code == 302
        assert response.url == f"{reverse('deliveries:create')}?purchase_request={purchase_request.pk}"

        purchase_request.refresh_from_db()
        assert purchase_request.status == "approved"


@pytest.mark.django_db
class TestPurchaseRequestVisibility:
    def test_pcm_approver_list_shows_other_users_requests(
        self,
        client,
        pcm_approver,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Bench power supply",
            vendor="Acme Components",
            currency="SGD",
            ordered_quantity=2,
            total_price="450.00",
            justification="Needed for prototype validation.",
            po_required=False,
            target_payment="2026-01-15",
            status="pending_pcm",
        )
        client.force_login(pcm_approver)

        response = client.get(reverse("orders:purchase-request-list"))

        assert response.status_code == 200
        assert len(response.context["purchase_requests"]) == 1

    def test_pcm_approver_can_view_other_users_request_detail(
        self,
        client,
        pcm_approver,
        regular_user,
        sample_project,
        sample_expense_category,
    ):
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Bench power supply",
            vendor="Acme Components",
            currency="SGD",
            ordered_quantity=2,
            total_price="450.00",
            justification="Needed for prototype validation.",
            po_required=False,
            target_payment="2026-01-15",
            status="pending_pcm",
        )
        client.force_login(pcm_approver)

        response = client.get(
            reverse("orders:purchase-request-detail", args=[purchase_request.pk])
        )

        assert response.status_code == 200


@pytest.mark.django_db
class TestPurchaseRequestDatasetExport:
    def test_requester_dataset_export_contains_one_row_per_line_item(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        monkeypatch,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Legacy fallback description",
            vendor="Coway",
            currency="USD",
            ordered_quantity=20,
            total_price=Decimal("995.00"),
            justification="Needed for evaluation.",
            po_required=False,
            target_payment="2026-05-20",
            status="approved",
        )
        item_one = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="AAA",
            quantity=5,
            unit_price=Decimal("100.00"),
            total_price=Decimal("500.00"),
            currency="USD",
        )
        item_two = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=2,
            product="BBB",
            quantity=15,
            unit_price=Decimal("33.00"),
            total_price=Decimal("495.00"),
            currency="USD",
        )
        delivery = DeliverySubmission.objects.create(
            purchase_request=purchase_request,
            requester=regular_user,
            vendor="Coway",
            currency="USD",
            delivered_quantity=19,
            total_price=Decimal("945.25"),
            status="partially_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=delivery,
            purchase_request_line_item=item_one,
            sequence=1,
            product="AAA",
            ordered_quantity=5,
            delivered_quantity=5,
            unit_price=Decimal("100.00"),
            total_price=Decimal("500.00"),
            currency="USD",
            status="fully_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=delivery,
            purchase_request_line_item=item_two,
            sequence=2,
            product="BBB",
            ordered_quantity=15,
            delivered_quantity=14,
            unit_price=Decimal("33.00"),
            total_price=Decimal("445.25"),
            currency="USD",
            status="partially_delivered",
        )
        PaymentRelease.objects.create(
            purchase_request=purchase_request,
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Standard payment",
            vendor="Coway",
            currency="USD",
            payment_type="standard",
            payment_quantity=19,
            total_price=Decimal("945.25"),
            justification="Pay delivered items.",
            po_number="PO-123",
            target_payment="2026-05-20",
            status="approved",
        )

        monkeypatch.setattr(
            "orders.export_service.convert_amount_to_sgd",
            lambda amount, currency: Decimal(str(amount)) * Decimal("1.35"),
        )

        response = client.get(reverse("orders:purchase-request-dataset-export"))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        content = response.content.decode("utf-8")
        assert "Request No.,Requester,Submitted Date,Last Updated,Project,MC Number,Expense Category,Vendor,Product,Currency,Unit Price,Quantity Ordered,Quantity Delivered,Outstanding Quantity,Line Total,Line Total in SGD,PO Number,Target Payment Date,Goods Recieve Status,Payment Release Status,Workflow Stage,Workflow Completed" in content
        assert f"{purchase_request.workflow_number},{regular_user.username},{purchase_request.created_at.strftime('%Y-%m-%d %H:%M:%S')}" in content
        assert ",AAA,USD,100.00,5,5,0,500.00,675.00,PO-123,2026-05-20,Partially Delivered,Payment Approved,Partial Delivery Follow-up,No" in content
        assert ",BBB,USD,33.00,15,14,1,495.00,668.25,PO-123,2026-05-20,Partially Delivered,Payment Approved,Partial Delivery Follow-up,No" in content

    def test_requester_dataset_export_only_includes_own_requests(
        self,
        client,
        regular_user,
        user_factory,
        sample_project,
        sample_expense_category,
        monkeypatch,
    ):
        other_user = user_factory(username="other_requester", role="requester")
        client.force_login(regular_user)

        own_pr = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Own request",
            vendor="Own Vendor",
            currency="SGD",
            ordered_quantity=1,
            total_price=Decimal("100.00"),
            justification="Own justification",
            po_required=False,
            target_payment="2026-05-20",
            status="approved",
        )
        PurchaseRequestLineItem.objects.create(
            purchase_request=own_pr,
            sequence=1,
            product="Own Product",
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            currency="SGD",
        )

        other_pr = PurchaseRequest.objects.create(
            requester=other_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Other request",
            vendor="Other Vendor",
            currency="SGD",
            ordered_quantity=1,
            total_price=Decimal("200.00"),
            justification="Other justification",
            po_required=False,
            target_payment="2026-05-21",
            status="approved",
        )
        PurchaseRequestLineItem.objects.create(
            purchase_request=other_pr,
            sequence=1,
            product="Other Product",
            quantity=1,
            unit_price=Decimal("200.00"),
            total_price=Decimal("200.00"),
            currency="SGD",
        )

        monkeypatch.setattr(
            "orders.export_service.convert_amount_to_sgd",
            lambda amount, currency: Decimal(str(amount)),
        )

        response = client.get(reverse("orders:purchase-request-dataset-export"))

        content = response.content.decode("utf-8")
        assert own_pr.workflow_number in content
        assert "Own Product" in content
        assert other_pr.workflow_number not in content
        assert "Other Product" not in content

    def test_requester_sap_reconciliation_export_uses_request_number_and_sgd_amount(
        self,
        client,
        regular_user,
        sample_project,
        sample_expense_category,
        monkeypatch,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequest.objects.create(
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Legacy fallback description",
            vendor="Coway",
            currency="USD",
            ordered_quantity=20,
            total_price=Decimal("995.00"),
            justification="Needed for evaluation.",
            po_required=False,
            target_payment="2026-05-20",
            status="approved",
        )
        PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="AAA",
            quantity=5,
            unit_price=Decimal("100.00"),
            total_price=Decimal("500.00"),
            currency="USD",
        )
        PaymentRelease.objects.create(
            purchase_request=purchase_request,
            requester=regular_user,
            expense_category=sample_expense_category,
            project=sample_project,
            description="Standard payment",
            vendor="Coway",
            currency="USD",
            payment_type="standard",
            payment_quantity=5,
            total_price=Decimal("500.00"),
            justification="Pay delivered items.",
            po_number="PO-123",
            target_payment="2026-05-20",
            status="approved",
        )

        monkeypatch.setattr(
            "orders.export_service.convert_amount_to_sgd",
            lambda amount, currency: Decimal(str(amount)) * Decimal("1.35"),
        )

        response = client.get(reverse("orders:purchase-request-sap-reconciliation-export"))

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Request No.,Ledger,Company Code,Fiscal Year,G/L Account,G/L Account: Long Text,Document Number,Document Type,Document Date,Posting Date,Company Code Currency Key,Company Code Currency Value,Text,Purchasing Document" in content
        assert f"{purchase_request.workflow_number},,,2026,,{sample_expense_category.name},,,{purchase_request.created_at.strftime('%Y-%m-%d')},,SGD,675.00,Coway - AAA - {purchase_request.workflow_number} - {sample_project.mc_number},PO-123" in content
