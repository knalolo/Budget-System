"""Integration tests for the orders API (PurchaseRequest endpoints).

URL structure notes:
- The orders router registers as "purchase-requests" inside the
  /api/v1/purchase-requests/ prefix, so the real list URL is:
  /api/v1/purchase-requests/purchase-requests/

Known bugs in source code (do NOT fix, just document):
- orders/api_views._get_role uses user.userprofile.role but the model
  uses related_name="profile". This makes role-based gating on approve/reject
  non-functional; all users appear as roleless and get 403 on those endpoints.
- PurchaseRequestCreateSerializer does not include 'id' in its response,
  so creates must be verified via a DB lookup.
"""
import pytest

from orders.models import PurchaseRequest
from orders.tests.factories import (
    ExpenseCategoryFactory,
    ProjectFactory,
    PurchaseRequestFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_LIST = "/api/v1/purchase-requests/purchase-requests/"


def _detail(pk):
    return f"{_LIST}{pk}/"


def _action(pk, action):
    return f"{_LIST}{pk}/{action}/"


def _create_payload(project, category):
    return {
        "expense_category": category.pk,
        "project": project.pk,
        "description": "Test description",
        "vendor": "Test Vendor",
        "currency": "SGD",
        "total_price": "500.00",
        "justification": "Needed for project",
        "po_required": False,
        "target_payment": "30 days",
    }


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListPurchaseRequests:
    def test_authenticated_user_sees_own_requests(self, api_client, regular_user):
        PurchaseRequestFactory(requester=regular_user)
        PurchaseRequestFactory(requester=regular_user)
        # Another user's PR should not appear (requester role only sees own)
        PurchaseRequestFactory()

        resp = api_client.get(_LIST)
        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.get(_LIST)
        assert resp.status_code == 403

    def test_list_returns_paginated_response(self, api_client):
        resp = api_client.get(_LIST)
        assert resp.status_code == 200
        assert "count" in resp.data
        assert "results" in resp.data


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreatePurchaseRequest:
    def test_create_returns_201(self, api_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = api_client.post(_LIST, payload, format="json")
        assert resp.status_code == 201

    def test_create_assigns_requester_from_token(self, api_client, regular_user):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = api_client.post(_LIST, payload, format="json")
        assert resp.status_code == 201
        # Verify via DB since CreateSerializer does not include 'id'
        pr = PurchaseRequest.objects.filter(requester=regular_user).first()
        assert pr is not None
        assert pr.requester == regular_user

    def test_create_generates_request_number(self, api_client, regular_user):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = api_client.post(_LIST, payload, format="json")
        assert resp.status_code == 201
        pr = PurchaseRequest.objects.filter(requester=regular_user).first()
        assert pr is not None
        assert pr.request_number.startswith("PR-")

    def test_create_unauthenticated_returns_403(self, anon_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()
        payload = _create_payload(project, category)
        resp = anon_client.post(_LIST, payload, format="json")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetrievePurchaseRequest:
    def test_retrieve_own_request(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user)
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 200
        assert resp.data["id"] == pr.pk

    def test_retrieve_other_users_request_returns_404_for_requester(self, api_client):
        # get_queryset filters by requester for non-approver role → 404
        pr = PurchaseRequestFactory()
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 404

    def test_retrieve_returns_correct_fields(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user)
        resp = api_client.get(_detail(pr.pk))
        assert resp.status_code == 200
        assert "request_number" in resp.data
        assert "status" in resp.data
        assert "vendor" in resp.data


# ---------------------------------------------------------------------------
# Submit action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubmitAction:
    def test_submit_draft_returns_200_and_pending_status(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="draft")
        resp = api_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 200
        assert resp.data["status"] == "pending_pcm"

    def test_submit_non_draft_returns_400(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 400

    def test_submit_unauthenticated_returns_403(self, anon_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="draft")
        resp = anon_client.post(_action(pr.pk, "submit"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Approve/Reject action
# (role checks are non-functional due to userprofile/profile naming bug;
#  all users appear roleless, so approve/reject returns 403 for everyone)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApproveAction:
    def test_requester_cannot_approve(self, api_client, regular_user):
        """Regular users get 403 on approve (no approver role due to the bug)."""
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 403

    def test_unauthenticated_cannot_approve(self, anon_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = anon_client.post(_action(pr.pk, "approve"))
        assert resp.status_code == 403


@pytest.mark.django_db
class TestRejectAction:
    def test_requester_cannot_reject(self, api_client, regular_user):
        """Regular users get 403 on reject (no approver role due to the bug)."""
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.post(_action(pr.pk, "reject"))
        assert resp.status_code == 403

    def test_unauthenticated_cannot_reject(self, anon_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = anon_client.post(_action(pr.pk, "reject"))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeletePurchaseRequest:
    def test_delete_draft_succeeds(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="draft")
        resp = api_client.delete(_detail(pr.pk))
        assert resp.status_code == 204

    def test_delete_non_draft_returns_400(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")
        resp = api_client.delete(_detail(pr.pk))
        assert resp.status_code == 400

    def test_delete_unauthenticated_returns_403(self, anon_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="draft")
        resp = anon_client.delete(_detail(pr.pk))
        assert resp.status_code == 403
