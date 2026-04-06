"""Factory-boy factories for the payments app."""
import factory

from orders.tests.factories import (
    ExpenseCategoryFactory,
    ProjectFactory,
    UserFactory,
)
from payments.models import PaymentRelease


class PaymentReleaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentRelease

    requester = factory.SubFactory(UserFactory)
    expense_category = factory.SubFactory(ExpenseCategoryFactory)
    project = factory.SubFactory(ProjectFactory)
    description = "Test payment release description"
    vendor = "Test Payment Vendor Pte Ltd"
    currency = "SGD"
    payment_type = "standard"
    payment_quantity = 1
    total_price = factory.Sequence(lambda n: 200 + n)
    justification = "Invoice payment for delivered goods"
    po_number = "N/A"
    target_payment = "30 days"
    status = "draft"
    purchase_request = None
