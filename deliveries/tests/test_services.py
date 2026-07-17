"""Unit tests for deliveries.services."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from deliveries.services import create_delivery_submission, update_delivery_submission
from orders.models import PurchaseRequestLineItem
from orders.tests.factories import PurchaseRequestFactory, UserFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestCreateDeliverySubmission:
    def test_create_partial_delivery_submission(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=10,
            total_price=1000,
        )

        submission = create_delivery_submission(
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 4,
                "total_price": 400,
                "status": "partially_delivered",
                "notes": "First batch only.",
                "purchase_request": purchase_request,
            },
            user=requester,
            files=[
                SimpleUploadedFile(
                    "delivery-order.pdf",
                    b"%PDF-1.4 delivery order",
                    content_type="application/pdf",
                )
            ],
        )

        assert submission.status == "partially_delivered"
        assert submission.delivered_quantity == 4
        assert purchase_request.delivered_quantity == 4
        assert purchase_request.remaining_quantity == 6

    def test_create_full_delivery_requires_remaining_quantity(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=10,
            total_price=1000,
        )

        with pytest.raises(ValueError):
            create_delivery_submission(
                data={
                    "vendor": purchase_request.vendor,
                    "currency": purchase_request.currency,
                    "delivered_quantity": 4,
                    "total_price": 400,
                    "status": "fully_delivered",
                    "notes": "",
                    "purchase_request": purchase_request,
                },
                user=requester,
                files=[],
            )

    def test_create_delivery_submission_keeps_pr_in_approved_execution_ready_stage(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=5,
            total_price=500,
            po_required=False,
        )

        submission = create_delivery_submission(
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 5,
                "total_price": 500,
                "status": "fully_delivered",
                "notes": "",
                "purchase_request": purchase_request,
            },
            user=requester,
            files=[
                SimpleUploadedFile(
                    "delivery-order.pdf",
                    b"%PDF-1.4 delivery order",
                    content_type="application/pdf",
                )
            ],
        )

        purchase_request.refresh_from_db()
        assert submission.purchase_request_id == purchase_request.id
        assert purchase_request.status == "approved"

    def test_payment_first_requires_approved_payment_before_goods_receive(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            execution_mode="payment_first",
            ordered_quantity=5,
            total_price=500,
        )

        with pytest.raises(ValueError, match="payment first"):
            create_delivery_submission(
                data={
                    "vendor": purchase_request.vendor,
                    "currency": purchase_request.currency,
                    "delivered_quantity": 5,
                    "total_price": 500,
                    "status": "fully_delivered",
                    "notes": "",
                    "purchase_request": purchase_request,
                },
                user=requester,
                files=[],
            )

        PaymentReleaseFactory(
            status="approved",
            purchase_request=purchase_request,
            requester=requester,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=5,
            total_price=500,
        )

        submission = create_delivery_submission(
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 5,
                "total_price": 500,
                "status": "fully_delivered",
                "notes": "",
                "purchase_request": purchase_request,
            },
            user=requester,
            files=[],
        )

        assert submission.status == "fully_delivered"

    def test_create_delivery_submission_with_line_items_saves_rows(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=5,
            total_price=350,
            currency="SGD",
        )
        line_item_1 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="Sensor head",
            quantity=2,
            unit_price=100,
            total_price=200,
            currency="SGD",
        )
        line_item_2 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=2,
            product="Control board",
            quantity=3,
            unit_price=50,
            total_price=150,
            currency="SGD",
        )

        submission = create_delivery_submission(
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 3,
                "total_price": 250,
                "status": "partially_delivered",
                "notes": "First batch only.",
                "purchase_request": purchase_request,
                "line_items": [
                    {
                        "purchase_request_line_item_id": line_item_1.id,
                        "sequence": 1,
                        "product": line_item_1.product,
                        "ordered_quantity": line_item_1.quantity,
                        "delivered_quantity": 2,
                        "unit_price": line_item_1.unit_price,
                        "total_price": 200,
                        "currency": "SGD",
                        "status": "fully_delivered",
                    },
                    {
                        "purchase_request_line_item_id": line_item_2.id,
                        "sequence": 2,
                        "product": line_item_2.product,
                        "ordered_quantity": line_item_2.quantity,
                        "delivered_quantity": 1,
                        "unit_price": line_item_2.unit_price,
                        "total_price": 50,
                        "currency": "SGD",
                        "status": "partially_delivered",
                    },
                ],
            },
            user=requester,
            files=[],
        )

        assert submission.line_items.count() == 2
        assert submission.delivered_quantity == 3
        assert submission.total_price == 250

    def test_update_partial_delivery_submission_accumulates_until_fully_delivered(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="approved",
            ordered_quantity=5,
            total_price=350,
            currency="SGD",
        )
        line_item_1 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="Sensor head",
            quantity=2,
            unit_price=100,
            total_price=200,
            currency="SGD",
        )
        line_item_2 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=2,
            product="Control board",
            quantity=3,
            unit_price=50,
            total_price=150,
            currency="SGD",
        )

        submission = create_delivery_submission(
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 3,
                "total_price": 250,
                "status": "partially_delivered",
                "notes": "First batch only.",
                "purchase_request": purchase_request,
                "line_items": [
                    {
                        "purchase_request_line_item_id": line_item_1.id,
                        "sequence": 1,
                        "product": line_item_1.product,
                        "ordered_quantity": line_item_1.quantity,
                        "delivered_quantity": 2,
                        "unit_price": line_item_1.unit_price,
                        "total_price": 200,
                        "currency": "SGD",
                        "status": "fully_delivered",
                    },
                    {
                        "purchase_request_line_item_id": line_item_2.id,
                        "sequence": 2,
                        "product": line_item_2.product,
                        "ordered_quantity": line_item_2.quantity,
                        "delivered_quantity": 1,
                        "unit_price": line_item_2.unit_price,
                        "total_price": 50,
                        "currency": "SGD",
                        "status": "partially_delivered",
                    },
                ],
            },
            user=requester,
            files=[],
        )

        updated = update_delivery_submission(
            submission=submission,
            data={
                "vendor": purchase_request.vendor,
                "currency": purchase_request.currency,
                "delivered_quantity": 5,
                "total_price": 350,
                "status": "fully_delivered",
                "notes": "Remaining quantity arrived.",
                "purchase_request": purchase_request,
                "line_items": [
                    {
                        "purchase_request_line_item_id": line_item_1.id,
                        "sequence": 1,
                        "product": line_item_1.product,
                        "ordered_quantity": line_item_1.quantity,
                        "delivered_quantity": 2,
                        "unit_price": line_item_1.unit_price,
                        "total_price": 200,
                        "currency": "SGD",
                        "status": "fully_delivered",
                    },
                    {
                        "purchase_request_line_item_id": line_item_2.id,
                        "sequence": 2,
                        "product": line_item_2.product,
                        "ordered_quantity": line_item_2.quantity,
                        "delivered_quantity": 3,
                        "unit_price": line_item_2.unit_price,
                        "total_price": 150,
                        "currency": "SGD",
                        "status": "fully_delivered",
                    },
                ],
            },
            user=requester,
            files=[],
        )

        purchase_request.refresh_from_db()
        assert updated.status == "fully_delivered"
        assert updated.delivered_quantity == 5
        assert updated.total_price == 350
        assert purchase_request.delivered_quantity == 5
        assert purchase_request.remaining_quantity == 0
