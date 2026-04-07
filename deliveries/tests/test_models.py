"""Unit tests for deliveries app models."""
import pytest

from deliveries.tests.factories import DeliverySubmissionFactory


@pytest.mark.django_db
class TestDeliverySubmissionModel:
    def test_create_submission(self):
        ds = DeliverySubmissionFactory()
        assert ds.pk is not None
        assert ds.status == "fully_delivered"

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
        ds = DeliverySubmissionFactory(status="partially_delivered")
        assert ds.is_submitted is True
        assert ds.is_saved is False

    def test_is_saved_property(self):
        ds = DeliverySubmissionFactory(status="saved")
        assert ds.is_saved is True
        assert ds.is_submitted is False

    def test_delivery_status_properties(self):
        partially_delivered = DeliverySubmissionFactory(status="partially_delivered")
        fully_delivered = DeliverySubmissionFactory(status="fully_delivered")
        short_closed = DeliverySubmissionFactory(status="short_closed")

        assert partially_delivered.is_partially_delivered is True
        assert fully_delivered.is_fully_delivered is True
        assert short_closed.is_short_closed is True

    def test_progress_properties_use_linked_purchase_request(self):
        from orders.tests.factories import PurchaseRequestFactory

        purchase_request = PurchaseRequestFactory(
            ordered_quantity=20,
            total_price=100,
            currency="SGD",
            status="ordered",
        )
        ds = DeliverySubmissionFactory(
            purchase_request=purchase_request,
            delivered_quantity=10,
            total_price=100,
            currency="SGD",
            status="partially_delivered",
        )

        assert ds.delivery_quantity_progress == "10 / 20"
        assert ds.delivery_value_progress == "SGD 50.00 / SGD 100.00"

    def test_progress_properties_show_plain_values_when_not_partially_delivered(self):
        from orders.tests.factories import PurchaseRequestFactory

        purchase_request = PurchaseRequestFactory(
            ordered_quantity=20,
            total_price=100,
            currency="SGD",
            status="ordered",
        )
        ds = DeliverySubmissionFactory(
            purchase_request=purchase_request,
            delivered_quantity=20,
            total_price=100,
            currency="SGD",
            status="fully_delivered",
        )

        assert ds.delivery_quantity_progress == "20"
        assert ds.delivery_value_progress == "SGD 100.00"
