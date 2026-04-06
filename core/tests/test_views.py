"""Dashboard view tests."""

import pytest
from django.urls import reverse

from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import PurchaseRequestFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestDashboardView:
    def test_purchase_requests_tab_excludes_ordered_requests_in_delivery_stage(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)
        visible_pr = PurchaseRequestFactory(requester=regular_user)
        moved_pr = PurchaseRequestFactory(requester=regular_user, status="ordered")

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert list(response.context["my_purchase_requests"]) == [visible_pr]
        assert response.context["stats"]["dashboard_prs_count"] == 1
        assert response.context["stats"]["total_prs"] == 2

    def test_requester_cards_track_delivery_stage_and_ready_for_payment(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)
        do_pending_pr = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=10,
        )
        partial_pr = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=10,
        )
        ready_pr = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=10,
        )
        pending_payment_pr = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=10,
        )

        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=partial_pr,
            delivered_quantity=4,
            status="partially_delivered",
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=ready_pr,
            delivered_quantity=10,
            status="fully_delivered",
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=pending_payment_pr,
            delivered_quantity=10,
            status="fully_delivered",
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=pending_payment_pr,
            status="pending_pcm",
            payment_type="standard",
            payment_quantity=10,
            total_price=1000,
        )

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert do_pending_pr in response.context["my_delivery_stage_requests"]
        assert partial_pr in response.context["my_delivery_stage_requests"]
        assert ready_pr in response.context["my_delivery_stage_requests"]
        assert response.context["stats"]["requester_pending_count"] == 1
        assert response.context["stats"]["requester_ready_for_payment_count"] == 1
        assert response.context["stats"]["requester_do_pending_count"] == 1
        assert response.context["stats"]["requester_partial_delivery_count"] == 1
