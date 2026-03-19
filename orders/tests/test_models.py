"""Unit tests for orders app models."""
import pytest

from core.models import SystemConfig
from orders.models import ExpenseCategory, Project, PurchaseRequest
from orders.tests.factories import (
    ExpenseCategoryFactory,
    ProjectFactory,
    PurchaseRequestFactory,
)


# ---------------------------------------------------------------------------
# Project model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProjectModel:
    def test_create_project(self):
        project = ProjectFactory()
        assert project.pk is not None
        assert project.mc_number.startswith("MC-")
        assert project.is_active is True

    def test_project_str(self):
        project = ProjectFactory(mc_number="MC-9999", name="Alpha")
        assert str(project) == "MC-9999 - Alpha"

    def test_project_ordering(self):
        ProjectFactory(mc_number="MC-0002")
        ProjectFactory(mc_number="MC-0001")
        numbers = list(Project.objects.values_list("mc_number", flat=True))
        assert numbers == sorted(numbers)


# ---------------------------------------------------------------------------
# ExpenseCategory model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExpenseCategoryModel:
    def test_create_category(self):
        cat = ExpenseCategoryFactory()
        assert cat.pk is not None
        assert cat.is_active is True

    def test_category_str(self):
        cat = ExpenseCategoryFactory(name="Prototype")
        assert str(cat) == "Prototype"

    def test_unique_name(self):
        from django.db import IntegrityError

        ExpenseCategoryFactory(name="Unique Cat")
        with pytest.raises(IntegrityError):
            ExpenseCategoryFactory(name="Unique Cat")


# ---------------------------------------------------------------------------
# PurchaseRequest model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPurchaseRequestModel:
    def test_create_purchase_request(self):
        pr = PurchaseRequestFactory()
        assert pr.pk is not None
        assert pr.status == "draft"

    def test_auto_request_number_generated(self):
        pr = PurchaseRequestFactory()
        assert pr.request_number
        assert pr.request_number.startswith("PR-")

    def test_request_number_sequential(self):
        """Two PRs on the same day get consecutive sequence numbers."""
        pr1 = PurchaseRequestFactory()
        pr2 = PurchaseRequestFactory()
        # Both start with PR- and have a different trailing sequence
        assert pr1.request_number != pr2.request_number

    def test_request_number_not_overwritten(self):
        """Saving an existing PR does not change its request_number."""
        pr = PurchaseRequestFactory()
        original = pr.request_number
        pr.vendor = "Updated Vendor"
        pr.save()
        pr.refresh_from_db()
        assert pr.request_number == original

    def test_is_draft_property(self):
        pr = PurchaseRequestFactory(status="draft")
        assert pr.is_draft is True
        assert pr.is_pending is False
        assert pr.is_approved is False
        assert pr.is_rejected is False

    def test_is_pending_property(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        assert pr.is_pending is True
        assert pr.is_draft is False

        pr2 = PurchaseRequestFactory(status="pending_final")
        assert pr2.is_pending is True

    def test_is_approved_property(self):
        pr = PurchaseRequestFactory(status="approved")
        assert pr.is_approved is True
        assert pr.is_draft is False

    def test_is_rejected_property(self):
        pr = PurchaseRequestFactory(status="rejected")
        assert pr.is_rejected is True

    def test_can_be_edited_and_deleted_draft(self):
        pr = PurchaseRequestFactory(status="draft")
        assert pr.can_be_edited is True
        assert pr.can_be_deleted is True

    def test_can_be_edited_and_deleted_non_draft(self):
        pr = PurchaseRequestFactory(status="pending_pcm")
        assert pr.can_be_edited is False
        assert pr.can_be_deleted is False

    def test_pr_str(self):
        pr = PurchaseRequestFactory(vendor="ACME Corp")
        assert "ACME Corp" in str(pr)

    def test_requires_po_with_threshold(self):
        """requires_po returns True when total_price meets the threshold."""
        SystemConfig.set_value("po_threshold_sgd", 1000)
        pr = PurchaseRequestFactory(currency="SGD", total_price=1500, po_required=False)
        assert pr.requires_po is True

    def test_requires_po_below_threshold(self):
        """requires_po returns False when total_price is below the threshold."""
        SystemConfig.set_value("po_threshold_sgd", 1000)
        pr = PurchaseRequestFactory(currency="SGD", total_price=500, po_required=False)
        assert pr.requires_po is False

    def test_requires_po_no_config_falls_back_to_field(self):
        """requires_po falls back to po_required when no config key exists."""
        pr = PurchaseRequestFactory(currency="SGD", po_required=True)
        # Remove any threshold key to ensure fallback
        SystemConfig.objects.filter(key="po_threshold_sgd").delete()
        assert pr.requires_po is True

    def test_requires_po_unknown_currency_falls_back(self):
        pr = PurchaseRequestFactory(currency="SGD", po_required=True)
        # Monkey-patch currency to something not in the map
        pr.currency = "JPY"
        assert pr.requires_po is True
