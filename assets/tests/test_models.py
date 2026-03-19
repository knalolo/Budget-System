"""Unit tests for assets app models."""
import pytest
from datetime import date
from decimal import Decimal

from assets.models import AssetItem, AssetRegistration


@pytest.mark.django_db
class TestAssetRegistrationModel:
    def test_create_registration(self, regular_user):
        reg = AssetRegistration.objects.create(
            requester=regular_user,
            status="draft",
        )
        assert reg.pk is not None
        assert reg.status == "draft"

    def test_default_status_is_draft(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        assert reg.status == "draft"

    def test_str_representation(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        result = str(reg)
        assert "AssetRegistration" in result
        assert "Draft" in result

    def test_item_count_is_zero_initially(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        assert reg.item_count == 0

    def test_item_count_increments_with_items(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        AssetItem.objects.create(registration=reg, asset_name="Laptop")
        AssetItem.objects.create(registration=reg, asset_name="Mouse")
        assert reg.item_count == 2


@pytest.mark.django_db
class TestAssetItemModel:
    def test_create_asset_item(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        item = AssetItem.objects.create(
            registration=reg,
            asset_name="Dell Laptop",
            asset_tag="AT-001",
            category="IT Equipment",
            serial_number="SN-12345",
            purchase_date=date(2025, 1, 15),
            purchase_cost=Decimal("1500.00"),
            supplier="Dell",
            location="Office A",
            department="Engineering",
            assigned_to="John Doe",
        )
        assert item.pk is not None
        assert item.asset_name == "Dell Laptop"

    def test_asset_item_str(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        item = AssetItem.objects.create(registration=reg, asset_name="Monitor")
        result = str(item)
        assert "Monitor" in result

    def test_optional_fields_can_be_blank(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        # Only required field is registration and asset_name
        item = AssetItem.objects.create(
            registration=reg,
            asset_name="Generic Item",
        )
        assert item.pk is not None
        assert item.asset_tag == ""
        assert item.serial_number == ""
        assert item.purchase_date is None
        assert item.purchase_cost is None
