"""Integration tests for PurchaseRequest API endpoints."""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from assets.models import AssetRegistration
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.models import PurchaseRequest
from orders.tests.factories import (
    ExpenseCategoryFactory,
    ProjectFactory,
    PurchaseRequestFactory,
    UserFactory,
)
from payments.tests.factories import PaymentReleaseFactory


_LIST = "/api/v1/purchase-requests/purchase-requests/"


def _detail(pk):
    return f"{_LIST}{pk}/"


def _action(pk, action):
    return f"{_LIST}{pk}/{action}/"


def _client_for(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


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


@pytest.mark.django_db
class TestListPurchaseRequests:
    def test_authenticated_user_sees_own_requests(self, api_client, regular_user):
        PurchaseRequestFactory(requester=regular_user)
        PurchaseRequestFactory(requester=regular_user)
        PurchaseRequestFactory()

        resp = api_client.get(_LIST)

        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_first_stage_approver_sees_all_requests(self, user_factory, regular_user):
        approver = user_factory(username="project_api_approver", role="project_approver")
        client = _client_for(approver)
        PurchaseRequestFactory(requester=regular_user)
        PurchaseRequestFactory()

        resp = client.get(_LIST)

        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.get(_LIST)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestCreatePurchaseRequest:
    def test_create_returns_201(self, api_client):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()

        resp = api_client.post(_LIST, _create_payload(project, category), format="json")

        assert resp.status_code == 201

    def test_create_assigns_requester_from_token(self, api_client, regular_user):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()

        resp = api_client.post(_LIST, _create_payload(project, category), format="json")

        assert resp.status_code == 201
        pr = PurchaseRequest.objects.filter(requester=regular_user).first()
        assert pr is not None
        assert pr.requester == regular_user

    def test_create_generates_request_number(self, api_client, regular_user):
        project = ProjectFactory()
        category = ExpenseCategoryFactory()

        resp = api_client.post(_LIST, _create_payload(project, category), format="json")

        assert resp.status_code == 201
        pr = PurchaseRequest.objects.filter(requester=regular_user).first()
        assert pr is not None
        assert pr.request_number.startswith("PR-")


@pytest.mark.django_db
class TestRetrievePurchaseRequest:
    def test_retrieve_own_request(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user)

        resp = api_client.get(_detail(pr.pk))

        assert resp.status_code == 200
        assert resp.data["id"] == pr.pk

    def test_retrieve_other_users_request_returns_404_for_requester(self, api_client):
        pr = PurchaseRequestFactory()

        resp = api_client.get(_detail(pr.pk))

        assert resp.status_code == 404

    def test_retrieve_other_users_request_returns_200_for_final_approver(self, user_factory):
        final_approver = user_factory(username="final_api_approver", role="final_approver")
        client = _client_for(final_approver)
        pr = PurchaseRequestFactory()

        resp = client.get(_detail(pr.pk))

        assert resp.status_code == 200
        assert resp.data["request_number"] == pr.workflow_number


@pytest.mark.django_db
class TestSubmitAction:
    def test_submit_draft_returns_200_and_pending_status(self, api_client, regular_user):
        UserFactory(project_approver=True)
        UserFactory(final_approver=True)
        pr = PurchaseRequestFactory(requester=regular_user, status="draft")

        resp = api_client.post(_action(pr.pk, "submit"))

        assert resp.status_code == 200
        assert resp.data["status"] == "pending_pcm"

    def test_submit_non_draft_returns_400(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")

        resp = api_client.post(_action(pr.pk, "submit"))

        assert resp.status_code == 400


@pytest.mark.django_db
class TestApproveAction:
    def test_requester_without_approver_permission_cannot_approve(self, api_client, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="pending_pcm")

        resp = api_client.post(_action(pr.pk, "approve"))

        assert resp.status_code == 403

    def test_project_approver_can_approve_project_request(self, user_factory):
        approver = user_factory(username="project_stage_user", role="project_approver")
        client = _client_for(approver)
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="project")

        resp = client.post(_action(pr.pk, "approve"), {"comment": "Looks good"}, format="json")

        assert resp.status_code == 200
        assert resp.data["status"] == "pending_final"

    def test_non_project_approver_cannot_approve_project_request(self, user_factory):
        approver = user_factory(username="non_project_stage_user", role="non_project_approver")
        client = _client_for(approver)
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="project")

        resp = client.post(_action(pr.pk, "approve"))

        assert resp.status_code == 403
        assert "project approver" in resp.data["detail"].lower()

    def test_requester_with_matching_first_stage_permission_can_self_approve(self, user_factory):
        approver = user_factory(
            username="self_project_submitter",
            role="project_approver",
            is_requester=True,
        )
        client = _client_for(approver)
        pr = PurchaseRequestFactory(
            requester=approver,
            status="pending_pcm",
            purchase_type="project",
        )

        resp = client.post(_action(pr.pk, "approve"), {"comment": "Self-approved"}, format="json")

        assert resp.status_code == 200
        assert resp.data["status"] == "pending_final"

    def test_final_approver_can_approve_final_stage(self, user_factory):
        approver = user_factory(username="final_stage_user", role="final_approver")
        client = _client_for(approver)
        pr = PurchaseRequestFactory(status="pending_final", purchase_type="office")

        resp = client.post(_action(pr.pk, "approve"), {"comment": "Approved"}, format="json")

        assert resp.status_code == 200
        assert resp.data["status"] == "approved"


@pytest.mark.django_db
class TestRejectAction:
    def test_office_approver_can_reject_office_request(self, user_factory):
        approver = user_factory(username="office_stage_user", role="office_approver")
        client = _client_for(approver)
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="office")

        resp = client.post(_action(pr.pk, "reject"), {"comment": "Need more detail"}, format="json")

        assert resp.status_code == 200
        assert resp.data["status"] == "rejected"

    def test_final_approver_cannot_reject_first_stage_item(self, user_factory):
        approver = user_factory(username="wrong_stage_final", role="final_approver")
        client = _client_for(approver)
        pr = PurchaseRequestFactory(status="pending_pcm", purchase_type="non_project")

        resp = client.post(_action(pr.pk, "reject"), {"comment": "Wrong stage"}, format="json")

        assert resp.status_code == 403
        assert "non-project approver" in resp.data["detail"].lower()


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

    def test_admin_can_delete_entire_workflow_from_non_draft_request(self, api_client_admin, admin_user, regular_user):
        pr = PurchaseRequestFactory(requester=regular_user, status="approved")
        payment = PaymentReleaseFactory(
            requester=regular_user,
            purchase_request=pr,
            project=pr.project,
            expense_category=pr.expense_category,
            status="pending_final",
            vendor=pr.vendor,
        )
        DeliverySubmissionFactory(
            requester=regular_user,
            purchase_request=pr,
            vendor=pr.vendor,
            currency=pr.currency,
            status="fully_delivered",
        )
        AssetRegistration.objects.create(
            requester=admin_user,
            purchase_request=pr,
            payment_release=payment,
        )

        resp = api_client_admin.delete(_detail(pr.pk))

        assert resp.status_code == 204
        assert not PurchaseRequest.objects.filter(pk=pr.pk).exists()
        assert not type(payment).objects.filter(pk=payment.pk).exists()
        assert AssetRegistration.objects.count() == 0
