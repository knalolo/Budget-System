"""Models for the assets app: AssetRegistration and AssetItem."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

# ---------------------------------------------------------------------------
# Status choices
# ---------------------------------------------------------------------------

ASSET_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("pending_export", "Pending Export"),
    ("exported", "Exported"),
    ("imported", "Imported"),
]


class AssetRegistration(models.Model):
    """A collection of asset items to be exported to AssetTiger."""

    payment_release = models.ForeignKey(
        "payments.PaymentRelease",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_registrations",
    )
    purchase_request = models.ForeignKey(
        "orders.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_registrations",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asset_registrations",
    )
    status = models.CharField(
        max_length=20,
        choices=ASSET_STATUS_CHOICES,
        default="draft",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AssetRegistration #{self.pk} ({self.get_status_display()})"

    @property
    def item_count(self) -> int:
        return self.items.count()

    @property
    def linked_purchase_request(self):
        if self.payment_release_id and self.payment_release:
            return self.payment_release.purchase_request
        return self.purchase_request


class AssetItem(models.Model):
    """A single asset line item within a registration batch."""

    registration = models.ForeignKey(
        AssetRegistration,
        on_delete=models.CASCADE,
        related_name="items",
    )
    asset_name = models.CharField(max_length=255)
    asset_tag = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=255, blank=True)
    serial_number = models.CharField(max_length=255, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    supplier = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    assigned_to = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.asset_name} (Reg #{self.registration_id})"
