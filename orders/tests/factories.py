"""Factory-boy factories for the orders app."""
import factory
from django.conf import settings
from django.contrib.auth.models import User

from orders.models import ExpenseCategory, Project, PurchaseRequest


class UserFactory(factory.django.DjangoModelFactory):
    class Params:
        requester = factory.Trait(
            profile_is_requester=True,
            profile_is_project_approver=False,
            profile_is_non_project_approver=False,
            profile_is_office_approver=False,
            profile_is_final_approver=False,
            profile_is_admin=False,
        )
        project_approver = factory.Trait(
            profile_is_requester=False,
            profile_is_project_approver=True,
            profile_is_non_project_approver=False,
            profile_is_office_approver=False,
            profile_is_final_approver=False,
            profile_is_admin=False,
        )
        non_project_approver = factory.Trait(
            profile_is_requester=False,
            profile_is_project_approver=False,
            profile_is_non_project_approver=True,
            profile_is_office_approver=False,
            profile_is_final_approver=False,
            profile_is_admin=False,
        )
        office_approver = factory.Trait(
            profile_is_requester=False,
            profile_is_project_approver=False,
            profile_is_non_project_approver=False,
            profile_is_office_approver=True,
            profile_is_final_approver=False,
            profile_is_admin=False,
        )
        final_approver = factory.Trait(
            profile_is_requester=False,
            profile_is_project_approver=False,
            profile_is_non_project_approver=False,
            profile_is_office_approver=False,
            profile_is_final_approver=True,
            profile_is_admin=False,
        )
        admin = factory.Trait(
            profile_is_requester=False,
            profile_is_project_approver=False,
            profile_is_non_project_approver=False,
            profile_is_office_approver=False,
            profile_is_final_approver=False,
            profile_is_admin=True,
        )

    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    profile_is_requester = True
    profile_is_project_approver = False
    profile_is_non_project_approver = False
    profile_is_office_approver = False
    profile_is_final_approver = False
    profile_is_admin = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        profile_flags = {
            "is_requester": kwargs.pop("profile_is_requester", True),
            "is_project_approver": kwargs.pop("profile_is_project_approver", False),
            "is_non_project_approver": kwargs.pop("profile_is_non_project_approver", False),
            "is_office_approver": kwargs.pop("profile_is_office_approver", False),
            "is_final_approver": kwargs.pop("profile_is_final_approver", False),
            "is_admin": kwargs.pop("profile_is_admin", False),
        }

        user = super()._create(model_class, *args, **kwargs)
        profile = user.profile
        profile.is_requester = profile_flags["is_requester"]
        profile.is_project_approver = profile_flags["is_project_approver"]
        profile.is_non_project_approver = profile_flags["is_non_project_approver"]
        profile.is_office_approver = profile_flags["is_office_approver"]
        profile.is_final_approver = profile_flags["is_final_approver"]
        profile.is_admin = profile_flags["is_admin"]
        profile.role = profile.legacy_role
        profile.save()
        return user


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
    purchase_type = settings.PURCHASE_TYPE_PROJECT
    execution_mode = settings.EXECUTION_MODE_DELIVERY_FIRST
    expense_category = factory.SubFactory(ExpenseCategoryFactory)
    project = factory.SubFactory(ProjectFactory)
    description = "Test purchase request description"
    vendor = "Test Vendor Pte Ltd"
    currency = "SGD"
    ordered_quantity = 1
    total_price = factory.Sequence(lambda n: 100 + n)
    justification = "Required for project work"
    po_required = False
    target_payment = "30 days"
    status = "draft"
