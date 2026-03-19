"""Factory-boy factories for the deliveries app."""
import factory

from deliveries.models import DeliverySubmission
from orders.tests.factories import UserFactory


class DeliverySubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeliverySubmission

    requester = factory.SubFactory(UserFactory)
    vendor = "Test Delivery Vendor"
    currency = "SGD"
    total_price = factory.Sequence(lambda n: 50 + n)
    status = "submitted"
    purchase_request = None
