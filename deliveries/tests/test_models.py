"""Unit tests for deliveries app models."""
import pytest

from deliveries.tests.factories import DeliverySubmissionFactory


@pytest.mark.django_db
class TestDeliverySubmissionModel:
    def test_create_submission(self):
        ds = DeliverySubmissionFactory()
        assert ds.pk is not None
        assert ds.status == "submitted"

    def test_auto_request_number_generated(self):
        ds = DeliverySubmissionFactory()
        assert ds.request_number
        assert ds.request_number.startswith("DO-")

    def test_request_number_sequential(self):
        ds1 = DeliverySubmissionFactory()
        ds2 = DeliverySubmissionFactory()
        assert ds1.request_number != ds2.request_number

    def test_request_number_not_overwritten_on_save(self):
        ds = DeliverySubmissionFactory()
        original = ds.request_number
        ds.vendor = "New Vendor"
        ds.save()
        ds.refresh_from_db()
        assert ds.request_number == original

    def test_str_representation(self):
        ds = DeliverySubmissionFactory(vendor="DelVendor")
        assert "DelVendor" in str(ds)

    def test_is_submitted_property(self):
        ds = DeliverySubmissionFactory(status="submitted")
        assert ds.is_submitted is True
        assert ds.is_saved is False

    def test_is_saved_property(self):
        ds = DeliverySubmissionFactory(status="saved")
        assert ds.is_saved is True
        assert ds.is_submitted is False
