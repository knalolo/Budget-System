"""Integration tests for the payments API (PaymentRelease endpoints).

Known issues in source code:
- PaymentReleaseCreateSerializer does not include 'id', so creates are
  verified via DB lookups.
- IsOwnerOrApprover uses user.userprofile.role (bug); role checks fail,
  non-owners get 403 (not 404, since queryset is unfiltered).
- The approve/reject endpoints have no explicit role check, but self-approval
  is blocked at the service layer.
"""
import pytest

from orders.tests.factories import ExpenseCategoryFactory, ProjectFactory
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
        # CreateSerializer does not return 'id'; verify via DB
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
        """Queryset is unfiltered; non-owners get 403 from IsOwnerOrApprover."""
        pr = PaymentReleaseFactory()
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 403

    def test_retrieve_includes_request_number(self, api_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user)
        resp = api_client.get(_detail(pr.pk))
        assert "request_number" in resp.data
        assert resp.data["request_number"].startswith("RP-")


# ---------------------------------------------------------------------------
# Submit action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitAction:
    def test_submit_draft_transitions_to_pending_pcm(self, api_client, regular_user):
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
# No role check in PaymentRelease API; service-layer self-approval is blocked.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApproveAction:
    def test_owner_self_approve_blocked_at_service_layer(self, api_client, regular_user):
        """The service blocks self-approval with a ValidationError → 400."""
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 400

    def test_unauthenticated_cannot_approve(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = anon_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Reject action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRejectAction:
    def test_owner_self_reject_blocked_at_service_layer(self, api_client, regular_user):
        """Service blocks self-approval (also applies to rejection) → 400."""
        pr = PaymentReleaseFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "reject"), {"comment": "Insufficient docs"})
        assert resp.status_code == 400

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

    def test_delete_unauthenticated_returns_403(self, anon_client, regular_user):
        pr = PaymentReleaseFactory(requester=regular_user, status="draft")
        resp = anon_client.delete(_detail(pr.pk))
        assert resp.status_code == 403
