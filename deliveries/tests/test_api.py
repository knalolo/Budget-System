"""Integration tests for the deliveries API (DeliverySubmission endpoints)."""
import io
import pytest

from deliveries.tests.factories import DeliverySubmissionFactory


_BASE = "/api/v1/delivery-submissions/"


def _detail(pk):
    return f"{_BASE}{pk}/"


def _create_payload():
    return {
        "vendor": "Delivery Vendor",
        "currency": "SGD",
        "total_price": "200.00",
    }


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListDeliverySubmissions:
    def test_authenticated_returns_200(self, api_client):
        resp = api_client.get(_BASE)
        assert resp.status_code == 200

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.get(_BASE)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateDeliverySubmission:
    def test_create_returns_201(self, api_client):
        payload = _create_payload()
        resp = api_client.post(_BASE, data=payload)
        assert resp.status_code == 201

    def test_create_sets_submitted_status(self, api_client):
        payload = _create_payload()
        resp = api_client.post(_BASE, data=payload)
        assert resp.status_code == 201
        assert resp.data["status"] == "submitted"

    def test_create_assigns_requester(self, api_client, regular_user):
        payload = _create_payload()
        resp = api_client.post(_BASE, data=payload)
        assert resp.status_code == 201
        from deliveries.models import DeliverySubmission

        ds = DeliverySubmission.objects.get(pk=resp.data["id"])
        assert ds.requester == regular_user

    def test_create_unauthenticated_returns_403(self, anon_client):
        payload = _create_payload()
        resp = anon_client.post(_BASE, data=payload)
        assert resp.status_code == 403

    def test_create_invalid_total_price_returns_400(self, api_client):
        payload = _create_payload()
        payload["total_price"] = "0.00"
        resp = api_client.post(_BASE, data=payload)
        assert resp.status_code == 400

    def test_create_with_auto_request_number(self, api_client):
        payload = _create_payload()
        resp = api_client.post(_BASE, data=payload)
        assert resp.status_code == 201
        assert resp.data["request_number"].startswith("DO-")


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetrieveDeliverySubmission:
    def test_retrieve_returns_200(self, api_client, regular_user):
        ds = DeliverySubmissionFactory(requester=regular_user)
        resp = api_client.get(_detail(ds.pk))
        assert resp.status_code == 200
        assert resp.data["id"] == ds.pk

    def test_retrieve_includes_attachments_key(self, api_client, regular_user):
        ds = DeliverySubmissionFactory(requester=regular_user)
        resp = api_client.get(_detail(ds.pk))
        assert "attachments" in resp.data


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteDeliverySubmission:
    def test_delete_returns_204(self, api_client, regular_user):
        ds = DeliverySubmissionFactory(requester=regular_user)
        resp = api_client.delete(_detail(ds.pk))
        assert resp.status_code == 204

    def test_delete_unauthenticated_returns_403(self, anon_client, regular_user):
        ds = DeliverySubmissionFactory(requester=regular_user)
        resp = anon_client.delete(_detail(ds.pk))
        assert resp.status_code == 403
