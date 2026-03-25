"""Dashboard view tests."""

import pytest
from django.urls import reverse

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
