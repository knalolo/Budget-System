"""Unit tests for deliveries.services."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from deliveries.services import create_delivery_submission
from orders.tests.factories import PurchaseRequestFactory, UserFactory


@pytest.mark.django_db
class TestCreateDeliverySubmission:
    def test_create_partial_delivery_submission(self):
        requester = UserFactory()
        purchase_request = PurchaseRequestFactory(
            requester=requester,
            status="ordered",
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
            status="ordered",
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

    def test_create_delivery_submission_moves_approved_request_into_ordered_stage(self):
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
        assert purchase_request.status == "ordered"
