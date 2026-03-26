"""Dashboard view tests."""

import pytest
from django.urls import reverse
from django.utils import timezone

from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import PurchaseRequestFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestDashboardView:
    def test_purchase_requests_tab_excludes_requests_with_payment_releases(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)
        visible_pr = PurchaseRequestFactory(requester=regular_user)
        moved_pr = PurchaseRequestFactory(requester=regular_user)
        PaymentReleaseFactory(requester=regular_user, purchase_request=moved_pr)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert list(response.context["my_purchase_requests"]) == [visible_pr]
        assert response.context["stats"]["dashboard_prs_count"] == 1
        assert response.context["stats"]["total_prs"] == 2

    def test_payment_releases_tab_excludes_items_with_delivery_submissions(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)
        delivered_pr = PurchaseRequestFactory(requester=regular_user)
        active_pr = PurchaseRequestFactory(requester=regular_user)
        delivered_payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=delivered_pr,
        )
        active_payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=active_pr,
        )
        DeliverySubmissionFactory(requester=regular_user, purchase_request=delivered_pr)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert list(response.context["my_payment_releases"]) == [active_payment]
        assert response.context["stats"]["dashboard_payments_count"] == 1
        assert response.context["stats"]["total_payments"] == 2

    def test_requester_summary_cards_track_pending_and_next_step_items(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)

        pending_pcm_pr = PurchaseRequestFactory(requester=regular_user, status="ordered")
        pending_final_pr = PurchaseRequestFactory(requester=regular_user, status="ordered")
        approved_payment_pr = PurchaseRequestFactory(requester=regular_user, status="ordered")

        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=pending_pcm_pr,
            status="pending_pcm",
            currency="SGD",
            total_price=100,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=pending_final_pr,
            status="pending_final",
            currency="USD",
            total_price=200,
        )
        approved_payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=approved_payment_pr,
            status="approved",
            currency="SGD",
            total_price=300,
        )
        approved_payment.updated_at = timezone.now()
        approved_payment.save(update_fields=["updated_at"])

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert response.context["stats"]["requester_pending_count"] == 2
        assert response.context["stats"]["requester_next_step_count"] == 1
        assert response.context["stats"]["approved_payment_spend_display"] == "SGD 300.00"
