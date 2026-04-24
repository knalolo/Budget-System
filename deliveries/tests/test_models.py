"""Unit tests for deliveries app models."""
import pytest

from deliveries.models import DeliverySubmissionLineItem
from deliveries.tests.factories import DeliverySubmissionFactory
from orders.models import PurchaseRequestLineItem


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

    def test_workflow_number_uses_linked_purchase_request(self):
        from orders.tests.factories import PurchaseRequestFactory

        purchase_request = PurchaseRequestFactory(request_number="PR-20260423-0002")
        ds = DeliverySubmissionFactory(
            purchase_request=purchase_request,
            request_number="DO-20260423-0001",
        )

        assert ds.workflow_number == "REQ-20260423-0002"

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
        assert ds.delivery_value_progress == "SGD 100.00 / SGD 100.00"

    def test_delivery_value_progress_uses_line_item_totals_when_present(self):
        from orders.tests.factories import PurchaseRequestFactory

        purchase_request = PurchaseRequestFactory(
            ordered_quantity=20,
            total_price=995,
            currency="SGD",
            status="ordered",
        )
        pr_line_1 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=1,
            product="AAA",
            quantity=5,
            unit_price="100.00",
            total_price="500.00",
            currency="SGD",
        )
        pr_line_2 = PurchaseRequestLineItem.objects.create(
            purchase_request=purchase_request,
            sequence=2,
            product="BBB",
            quantity=15,
            unit_price="33.00",
            total_price="495.00",
            currency="SGD",
        )
        ds = DeliverySubmissionFactory(
            purchase_request=purchase_request,
            delivered_quantity=19,
            total_price=895,
            currency="SGD",
            status="partially_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=ds,
            purchase_request_line_item=pr_line_1,
            sequence=1,
            product="AAA",
            ordered_quantity=5,
            delivered_quantity=4,
            unit_price="100.00",
            total_price="400.00",
            currency="SGD",
            status="partially_delivered",
        )
        DeliverySubmissionLineItem.objects.create(
            delivery_submission=ds,
            purchase_request_line_item=pr_line_2,
            sequence=2,
            product="BBB",
            ordered_quantity=15,
            delivered_quantity=15,
            unit_price="33.00",
            total_price="495.00",
            currency="SGD",
            status="fully_delivered",
        )

        assert ds.delivery_value == 895
        assert ds.delivery_value_progress == "SGD 895.00 / SGD 995.00"

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
