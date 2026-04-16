"""Template-view tests for delivery submissions."""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from deliveries.models import DeliverySubmission
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.models import PurchaseRequestLineItem
from orders.tests.factories import PurchaseRequestFactory, UserFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestDeliverySubmissionDeleteView:
    def test_requester_can_delete_own_delivery_submission(self, client, regular_user):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=200,
        )
        submission = DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=10,
            total_price=100,
            status="partially_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
        )
        client.force_login(regular_user)

        response = client.post(reverse("deliveries:delete", args=[submission.pk]))

        assert response.status_code == 302
        purchase_request.refresh_from_db()
        assert purchase_request.delivered_quantity == 0
        assert purchase_request.remaining_quantity == 20

    def test_other_user_cannot_delete_delivery_submission(self, client, regular_user):
        other_user = UserFactory()
        submission = DeliverySubmissionFactory(requester=other_user)
        client.force_login(regular_user)

        response = client.post(reverse("deliveries:delete", args=[submission.pk]))

        assert response.status_code == 403


@pytest.mark.django_db
class TestDeliverySubmissionListView:
    def test_list_shows_quantity_and_value_progress(self, client, regular_user):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=100,
            currency="SGD",
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=10,
            total_price=100,
            status="partially_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
        )
        client.force_login(regular_user)

        response = client.get(reverse("deliveries:list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "10 / 20" in content
        assert "SGD 50.00 / SGD 100.00" in content

    def test_list_keeps_plain_values_for_fully_delivered_rows(self, client, regular_user):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=100,
            currency="SGD",
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=20,
            total_price=100,
            status="fully_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
        )
        client.force_login(regular_user)

        response = client.get(reverse("deliveries:list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "20 / 20" not in content
        assert "SGD 100.00 / SGD 100.00" not in content

    def test_requester_cannot_delete_after_payment_enters_approval_flow(self, client, regular_user):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=200,
        )
        submission = DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=10,
            total_price=100,
            status="partially_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            status="pending_pcm",
            payment_type="standard",
            payment_quantity=10,
            total_price=100,
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.post(reverse("deliveries:delete", args=[submission.pk]))

        assert response.status_code == 403


@pytest.mark.django_db
class TestDeliverySubmissionCreateView:
    def test_create_with_line_items_aggregates_delivery_totals(self, client, regular_user, sample_project, sample_expense_category, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            project=sample_project,
            expense_category=sample_expense_category,
            status="ordered",
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
        client.force_login(regular_user)
        upload = SimpleUploadedFile(
            "delivery-order.pdf",
            b"%PDF-1.4 delivery order",
            content_type="application/pdf",
        )

        response = client.post(
            reverse("deliveries:create"),
            data={
                "purchase_request": purchase_request.pk,
                "vendor": purchase_request.vendor,
                "notes": "First batch.",
                "line_items_json": json.dumps(
                    [
                        {
                            "purchase_request_line_item_id": line_item_1.id,
                            "sequence": 1,
                            "product": "Sensor head",
                            "ordered_quantity": 2,
                            "delivered_quantity": 2,
                            "unit_price": "100.00",
                            "currency": "SGD",
                            "status": "fully_delivered",
                        },
                        {
                            "purchase_request_line_item_id": line_item_2.id,
                            "sequence": 2,
                            "product": "Control board",
                            "ordered_quantity": 3,
                            "delivered_quantity": 1,
                            "unit_price": "50.00",
                            "currency": "SGD",
                            "status": "partially_delivered",
                        },
                    ]
                ),
                "files": [upload],
            },
        )

        assert response.status_code == 302
        submission = DeliverySubmission.objects.get(requester=regular_user, purchase_request=purchase_request)
        assert submission.delivered_quantity == 3
        assert str(submission.total_price) == "250.00"
        assert submission.line_items.count() == 2
