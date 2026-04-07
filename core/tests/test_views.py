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

    def test_pcm_pending_approval_list_marks_advance_payment_without_goods_recieve(
        self,
        client,
        pcm_approver,
    ):
        purchase_request = PurchaseRequestFactory(
            status="ordered",
            ordered_quantity=8,
        )
        PaymentReleaseFactory(
            requester=purchase_request.requester,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=8,
            total_price=800,
            status="pending_pcm",
            vendor=purchase_request.vendor,
        )
        client.force_login(pcm_approver)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Advance Payment" in content
        assert "No Goods recieve" in content

    def test_requester_dashboard_highlights_approved_advance_payments_still_needing_do(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=20,
            total_price=1000,
            status="approved",
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert response.context["stats"]["requester_do_still_required_count"] == 1
        assert len(response.context["requester_action_items"]) == 1
        content = response.content.decode()
        assert "Your Next Actions" in content
        assert "Advance payment approved. Goods recieve is still outstanding" in content
        assert "Create Goods recieve" in content

    def test_requester_dashboard_does_not_offer_ready_for_payment_after_full_advance_payment(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=1000,
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=20,
            status="fully_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            total_price=1000,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=20,
            total_price=1000,
            status="approved",
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        assert response.context["requester_action_items"] == []
        content = response.content.decode()
        assert "Ready For Payment" not in content

    def test_requester_dashboard_shows_approved_pr_as_next_action_before_ordering(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="approved",
            ordered_quantity=2,
            po_required=False,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        action_items = response.context["requester_action_items"]
        assert len(action_items) == 1
        assert action_items[0]["title"] == purchase_request.request_number
        assert action_items[0]["label"] == "Choose Next Step"
        content = response.content.decode()
        assert "Track Goods recieve" in content
        assert "Request Advance Payment" in content
        assert "Open PR" in content

    def test_requester_dashboard_shows_payment_draft_as_next_action(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=5,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            status="draft",
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Complete Payment Draft" in content
        assert "This payment release is still in draft." in content

    def test_goods_recieve_panel_marks_fully_paid_and_fully_delivered_request_as_completed(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=20,
            total_price=1000,
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=20,
            status="fully_delivered",
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            total_price=1000,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            payment_type="advance",
            payment_quantity=20,
            total_price=1000,
            status="approved",
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Completed" in content
        assert "Payment In Progress" not in content
