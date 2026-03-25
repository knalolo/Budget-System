"""DRF serializers for AssetRegistration and AssetItem."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from payments.models import PaymentRelease

from .models import AssetItem, AssetRegistration

User = get_user_model()


class UserBriefSerializer(serializers.ModelSerializer):
    """Minimal user representation for embedding in other serializers."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# AssetItem
# ---------------------------------------------------------------------------


class AssetItemSerializer(serializers.ModelSerializer):
    """Full serializer for a single asset item."""

    class Meta:
        model = AssetItem
        fields = [
            "id",
            "registration",
            "asset_name",
            "asset_tag",
            "category",
            "serial_number",
            "purchase_date",
            "purchase_cost",
            "supplier",
            "location",
            "department",
            "assigned_to",
            "notes",
        ]
        read_only_fields = ["id"]


class AssetItemWriteSerializer(serializers.ModelSerializer):
    """Serializer for writing asset items (without registration FK on input)."""

    class Meta:
        model = AssetItem
        fields = [
            "id",
            "asset_name",
            "asset_tag",
            "category",
            "serial_number",
            "purchase_date",
            "purchase_cost",
            "supplier",
            "location",
            "department",
            "assigned_to",
            "notes",
        ]
        read_only_fields = ["id"]


# ---------------------------------------------------------------------------
# AssetRegistration – list
# ---------------------------------------------------------------------------


class AssetRegistrationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    requester = UserBriefSerializer(read_only=True)
    item_count = serializers.IntegerField(source="item_count", read_only=True)
    payment_release = serializers.PrimaryKeyRelatedField(read_only=True)
    purchase_request = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AssetRegistration
        fields = [
            "id",
            "payment_release",
            "purchase_request",
            "requester",
            "status",
            "item_count",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# AssetRegistration – detail
# ---------------------------------------------------------------------------


class AssetRegistrationDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail, create, and update operations."""

    requester = UserBriefSerializer(read_only=True)
    items = AssetItemWriteSerializer(many=True, required=False)
    item_count = serializers.IntegerField(source="item_count", read_only=True)
    payment_release = serializers.PrimaryKeyRelatedField(
        queryset=PaymentRelease.objects.filter(status="approved"),
        required=False,
        allow_null=True,
    )
    purchase_request = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AssetRegistration
        fields = [
            "id",
            "payment_release",
            "purchase_request",
            "requester",
            "status",
            "notes",
            "item_count",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requester",
            "item_count",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data: dict) -> AssetRegistration:
        items_data = validated_data.pop("items", [])
        request = self.context["request"]
        payment_release = validated_data.get("payment_release")
        registration = AssetRegistration.objects.create(
            requester=request.user,
            purchase_request=(
                payment_release.purchase_request if payment_release is not None else None
            ),
            **validated_data,
        )
        for item_data in items_data:
            AssetItem.objects.create(registration=registration, **item_data)
        return registration

    def update(self, instance: AssetRegistration, validated_data: dict) -> AssetRegistration:
        items_data = validated_data.pop("items", None)
        payment_release_supplied = "payment_release" in validated_data

        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if payment_release_supplied:
            instance.purchase_request = (
                instance.payment_release.purchase_request
                if instance.payment_release is not None
                else None
            )
        instance.save()

        # Replace items only when explicitly provided
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                AssetItem.objects.create(registration=instance, **item_data)

        return instance
