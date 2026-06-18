"""Integration tests for the payments API (PaymentRelease endpoints)."""

import pytest

from assets.models import AssetRegistration
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.tests.factories import ExpenseCategoryFactory, ProjectFactory, PurchaseRequestFactory, UserFactory
from payments.models import PaymentRelease
from payments.tests.factories import PaymentReleaseFactory


_BASE = "/api/v1/payment-releases/"


def _detail(pk):
    return f"{_BASE}{pk}/"


def _action(pk, action):
    return f"{_BASE}{pk}/{action}/"


def _create_payload(project, category):
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Invoice payment",
        "vendor": "Some Vendor",
        "currency": "SGD",
        "total_price": "1000.00",
        "justification": "Invoice settled",
        "po_number": "N/A",
        "target_payment": "30 days",
    }


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListPaymentReleases:
    def test_authenticated_returns_200(self, api_client, regular_user):
        PaymentReleaseFactory(requester=regular_user)
        resp = api_client.get(_BASE)
        assert resp.status_code == 200

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.get(_BASE)
        assert resp.status_code == 403

    def test_list_returns_paginated_results(self, api_client):
        resp = api_client.get(_BASE)
        assert "count" in resp.data
        assert "results" in resp.data


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreatePaymentRelease:
    def test_create_returns_201(self, api_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = api_client.post(_BASE, payload, format="json")
        assert resp.status_code == 201

    def test_create_assigns_requester(self, api_client, regular_user):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = api_client.post(_BASE, payload, format="json")
        assert resp.status_code == 201
        pr = PaymentRelease.objects.filter(requester=regular_user).first()
        assert pr is not None
        assert pr.requester == regular_user

    def test_create_unauthenticated_returns_403(self, anon_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = anon_client.post(_BASE, payload, format="json")
        assert resp.status_code == 403

    def test_create_invalid_total_price_returns_400(self, api_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        payload["total_price"] = "-10.00"
        resp = api_client.post(_BASE, payload, format="json")
        assert resp.status_code == 400

    def test_create_empty_po_number_returns_400(self, api_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        payload["po_number"] = "   "
        resp = api_client.post(_BASE, payload, format="json")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetrievePaymentRelease:
    def test_retrieve_own_returns_200(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user)
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 200
        assert resp.data["id"] == pr.pk

    def test_retrieve_other_users_returns_403(self, api_client):
        pr = PaymentReleaseFactory()
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 403

    def test_retrieve_includes_request_number(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user)
        resp = api_client.get(_detail(pr.pk))
        assert "request_number" in resp.data
        assert resp.data["request_number"] == pr.workflow_number


# ---------------------------------------------------------------------------
# Submit action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitAction:
    def test_submit_draft_transitions_to_pending_pcm(self, api_client, regular_user):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PaymentReleaseFactory(requester=regular_user, status="draft")
        resp = api_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 200
        assert resp.data["status"] == "pending_pcm"

    def test_submit_non_draft_returns_400(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 400

    def test_submit_unauthenticated_returns_403(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="draft")
        resp = anon_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Approve action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApproveAction:
    def test_requester_without_approver_permission_cannot_approve(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 403

    def test_unauthenticated_cannot_approve(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = anon_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Reject action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRejectAction:
    def test_requester_without_approver_permission_cannot_reject(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "reject"), {"comment": "Insufficient docs"})
        assert resp.status_code == 403

    def test_unauthenticated_cannot_reject(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = anon_client.post(_action(pr.pk, "reject"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeletePaymentRelease:
    def test_delete_draft_returns_204(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="draft")
        resp = api_client.delete(_detail(pr.pk))
        assert resp.status_code == 204

    def test_delete_non_draft_returns_400(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.delete(_detail(pr.pk))
        assert resp.status_code == 400

    def test_admin_can_delete_linked_workflow_from_non_draft_payment(
        self,
        api_client_admin,
        admin_user,
        regular_user,
    ):
        purchase_request = PurchaseRequestFactory(requester=regular_user, status="approved")
        payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            project=purchase_request.project,
            expense_category=purchase_request.expense_category,
            status="pending_pcm",
            vendor=purchase_request.vendor,
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=purchase_request,
            vendor=purchase_request.vendor,
            currency=purchase_request.currency,
            status="partially_delivered",
        )
        AssetRegistration.objects.create(
            requester=admin_user,
            purchase_request=purchase_request,
            payment_release=payment,
        )

        resp = api_client_admin.delete(_detail(payment.pk))

        assert resp.status_code == 204
        assert not PaymentRelease.objects.filter(pk=payment.pk).exists()
        assert not purchase_request.__class__.objects.filter(pk=purchase_request.pk).exists()
        assert AssetRegistration.objects.count() == 0

    def test_delete_unauthenticated_returns_403(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="draft")
        resp = anon_client.delete(_detail(pr.pk))
        assert resp.status_code == 403
