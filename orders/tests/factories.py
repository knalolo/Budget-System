"""Factory-boy factories for the orders app."""
import factory
from django.contrib.auth.models import User

from orders.models import ExpenseCategory, Project, PurchaseRequest


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    mc_number = factory.Sequence(lambda n: f"MC-{n:04d}")
    name = factory.Sequence(lambda n: f"Project {n}")
    is_active = True


class ExpenseCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExpenseCategory

    name = factory.Sequence(lambda n: f"Category {n}")
    is_active = True


class PurchaseRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PurchaseRequest

    requester = factory.SubFactory(UserFactory)
    expense_category = factory.SubFactory(ExpenseCategoryFactory)
    project = factory.SubFactory(ProjectFactory)
    description = "Test purchase request description"
    vendor = "Test Vendor Pte Ltd"
    currency = "SGD"
    total_price = factory.Sequence(lambda n: 100 + n)
    justification = "Required for project work"
    po_required = False
    target_payment = "30 days"
    status = "draft"
