"""Dashboard view tests."""

import pytest
from django.urls import reverse

from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import ProjectFactory, PurchaseRequestFactory
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestDashboardView:
    def test_approver_dashboard_shows_yearly_completed_spend_by_mc_number(
        self,
        client,
        pcm_approver,
        monkeypatch,
    ):
        general_project = ProjectFactory(mc_number="GENERAL", name="General")
        power_project = ProjectFactory(mc_number="MC004574", name="Power Cell")
        display_project = ProjectFactory(mc_number="MC004676", name="Display Module")
        sensor_project = ProjectFactory(mc_number="MC004680", name="U-Shape Sensor")

        completed_general = PurchaseRequestFactory(
            project=general_project,
            status="ordered",
            currency="SGD",
            total_price=100,
            ordered_quantity=5,
        )
        completed_power = PurchaseRequestFactory(
            project=power_project,
            status="ordered",
            currency="USD",
            total_price=50,
            ordered_quantity=2,
        )
        incomplete_display = PurchaseRequestFactory(
            project=display_project,
            status="approved",
            currency="SGD",
            total_price=300,
            ordered_quantity=3,
        )
        future_sensor = PurchaseRequestFactory(
            project=sensor_project,
            status="ordered",
            currency="SGD",
            total_price=80,
            ordered_quantity=4,
        )

        DeliverySubmissionFactory(
            requester=completed_general.requester,
            purchase_request=completed_general,
            delivered_quantity=5,
            status="fully_delivered",
            vendor=completed_general.vendor,
            currency=completed_general.currency,
            total_price=100,
        )
        PaymentReleaseFactory(
            requester=completed_general.requester,
            purchase_request=completed_general,
            project=completed_general.project,
            expense_category=completed_general.expense_category,
            status="approved",
            payment_type="standard",
            payment_quantity=5,
            total_price=100,
            vendor=completed_general.vendor,
        )

        DeliverySubmissionFactory(
            requester=completed_power.requester,
            purchase_request=completed_power,
            delivered_quantity=2,
            status="fully_delivered",
            vendor=completed_power.vendor,
            currency=completed_power.currency,
            total_price=50,
        )
        PaymentReleaseFactory(
            requester=completed_power.requester,
            purchase_request=completed_power,
            project=completed_power.project,
            expense_category=completed_power.expense_category,
            status="approved",
            payment_type="standard",
            payment_quantity=2,
            total_price=50,
            vendor=completed_power.vendor,
        )

        DeliverySubmissionFactory(
            requester=future_sensor.requester,
            purchase_request=future_sensor,
            delivered_quantity=4,
            status="fully_delivered",
            vendor=future_sensor.vendor,
            currency=future_sensor.currency,
            total_price=80,
        )
        PaymentReleaseFactory(
            requester=future_sensor.requester,
            purchase_request=future_sensor,
            project=future_sensor.project,
            expense_category=future_sensor.expense_category,
            status="approved",
            payment_type="standard",
            payment_quantity=4,
            total_price=80,
            vendor=future_sensor.vendor,
        )
        PurchaseRequestFactory(
            project=display_project,
            status="pending_pcm",
        )

        completed_general.created_at = completed_general.updated_at = completed_general.created_at.replace(year=2026)
        completed_general.save(update_fields=["created_at", "updated_at"])
        completed_power.created_at = completed_power.updated_at = completed_power.created_at.replace(year=2026)
        completed_power.save(update_fields=["created_at", "updated_at"])
        future_sensor.created_at = future_sensor.updated_at = future_sensor.created_at.replace(year=2027)
        future_sensor.save(update_fields=["created_at", "updated_at"])

        def fake_convert(amount, currency):
            if currency == "USD":
                return amount * 2
            return amount

        monkeypatch.setattr("core.views.convert_amount_to_sgd", fake_convert)
        client.force_login(pcm_approver)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        stats = response.context["stats"]
        assert stats["total_prs"] == 5
        yearly_rows = stats["approver_yearly_spend_rows"]
        assert yearly_rows[0]["year"] == 2027
        assert yearly_rows[0]["total_sgd"] == 80
        assert yearly_rows[1]["year"] == 2026
        assert yearly_rows[1]["total_sgd"] == 200
        by_mc_2026 = {
            row["mc_number"]: row["amount_sgd"]
            for row in yearly_rows[1]["project_rows"]
        }
        assert by_mc_2026["GENERAL"] == 100
        assert by_mc_2026["MC004574"] == 100
        assert by_mc_2026["MC004676"] == 0
        assert by_mc_2026["MC004680"] == 0

        content = response.content.decode()
        assert "Completed Spend by Year" in content
        assert "Total Requests" not in content
        assert "Pending My Approval" not in content
        assert "Approved This Month" not in content
        assert "Spend This Month" not in content

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
            status="approved",
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
        action_item = response.context["requester_action_items"][0]
        assert action_item["title"] == purchase_request.workflow_number
        assert action_item["label"] == "Goods recieve Still Required"
        content = response.content.decode()
        assert "Your Next Actions" in content
        assert "Payment has already been submitted. Goods recieve is still required to finish this request." in content
        assert "Submit Goods recieve" in content

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
        assert action_items[0]["title"] == purchase_request.workflow_number
        assert action_items[0]["label"] == "Choose Next Step"
        content = response.content.decode()
        assert "Submit Goods recieve" in content
        assert "Submit Payment" in content
        assert "Open PR" in content

    def test_requester_dashboard_keeps_payment_only_after_goods_submission(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=5,
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
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        action_items = response.context["requester_action_items"]
        assert len(action_items) == 1
        assert action_items[0]["label"] == "Payment Still Required"
        assert action_items[0]["primary_text"] == "Submit Payment"
        assert action_items[0]["secondary_text"] is None
        content = response.content.decode()
        assert "Submit Goods recieve" not in content
        assert "Submit Payment" in content

    def test_requester_dashboard_keeps_goods_only_after_payment_submission(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="approved",
            ordered_quantity=5,
        )
        PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            status="pending_pcm",
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        action_items = response.context["requester_action_items"]
        assert len(action_items) == 1
        assert action_items[0]["label"] == "Goods recieve Still Required"
        assert action_items[0]["primary_text"] == "Submit Goods recieve"
        assert action_items[0]["secondary_text"] == "Open Payment"
        content = response.content.decode()
        assert "Submit Goods recieve" in content
        assert "Submit Payment" not in content
        assert "Waiting for PCM / Final approval before payment can proceed." in content

    def test_requester_dashboard_keeps_partial_delivery_follow_up_until_fully_delivered(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=10,
        )
        delivery_submission = DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            delivered_quantity=4,
            total_price=400,
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
            payment_quantity=4,
            total_price=400,
            vendor=purchase_request.vendor,
        )
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        action_items = response.context["requester_action_items"]
        assert len(action_items) == 1
        assert action_items[0]["label"] == "Partial Delivery Follow-up"
        assert action_items[0]["primary_text"] == "Continue Goods recieve"
        assert action_items[0]["primary_url"] == reverse("deliveries:update", args=[delivery_submission.pk])
        assert action_items[0]["secondary_text"] == "Open Payment"
        content = response.content.decode()
        assert "Keep updating the same Goods recieve record until all goods arrive." in content

    def test_requester_dashboard_uses_linked_payment_draft_in_pr_action_item(
        self,
        client,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(
            requester=regular_user,
            status="ordered",
            ordered_quantity=5,
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
        action_items = response.context["requester_action_items"]
        assert len(action_items) == 1
        assert action_items[0]["primary_text"] == "Open Payment Draft"
        content = response.content.decode()
        assert "Complete Payment Draft" not in content
        assert "Open Payment Draft" in content

    def test_requester_dashboard_shows_only_new_pr_quick_action(
        self,
        client,
        regular_user,
    ):
        client.force_login(regular_user)

        response = client.get(reverse("core:dashboard"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "New PR" in content
        assert "New Goods recieve" not in content
        assert "New Payment" not in content

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
