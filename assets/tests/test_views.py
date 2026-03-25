"""View tests for the assets app."""

import json

import pytest
from django.urls import reverse

from assets.models import AssetRegistration
from orders.tests.factories import PurchaseRequestFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestAssetRegistrationCreateView:
    def test_create_links_to_approved_payment_release_and_purchase_request(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="approved",
        )
        payment_release = PaymentReleaseFactory(
            requester=regular_user,
            status="approved",
            purchase_request=purchase_request,
        )

        response = client.post(
            reverse("assets:create"),
            data={
                "payment_release": payment_release.pk,
                "notes": "Register approved assets",
                "items_json": json.dumps(
                    [
                        {
                            "asset_name": "Oscilloscope",
                            "asset_tag": "AT-001",
                            "category": "Lab Equipment",
                            "serial_number": "SN-001",
                            "purchase_date": "2026-03-25",
                            "purchase_cost": "1500.00",
                            "supplier": "NUS",
                            "location": "Lab A",
                            "department": "Engineering",
                            "assigned_to": "Alice",
                            "notes": "Approved payment release",
                        }
                    ]
                ),
            },
        )

        registration = AssetRegistration.objects.get()
        assert response.status_code == 302
        assert registration.payment_release == payment_release
        assert registration.purchase_request == purchase_request

    def test_form_only_displays_approved_payment_releases(self, client, regular_user):
        client.force_login(regular_user)
        approved_payment = PaymentReleaseFactory(
            requester=regular_user,
            status="approved",
            request_number="RP-APPROVED-0001",
            vendor="Coway",
        )
        pending_payment = PaymentReleaseFactory(
            requester=regular_user,
            status="pending_final",
            request_number="RP-PENDING-0001",
            vendor="Digikey",
        )

        response = client.get(reverse("assets:create"))

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert approved_payment.request_number in content
        assert pending_payment.request_number not in content
