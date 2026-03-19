"""Forms for the assets app."""

from django import forms

from orders.models import PurchaseRequest

from .models import AssetItem, AssetRegistration


class AssetRegistrationForm(forms.ModelForm):
    """Form for the top-level AssetRegistration record."""

    purchase_request = forms.ModelChoiceField(
        queryset=PurchaseRequest.objects.filter(status="approved").order_by(
            "-created_at"
        ),
        required=False,
        empty_label="-- None (standalone registration) --",
        help_text="Optionally link this registration to an approved purchase request.",
    )

    class Meta:
        model = AssetRegistration
        fields = ["purchase_request", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class AssetItemForm(forms.ModelForm):
    """Form for a single asset item."""

    class Meta:
        model = AssetItem
        fields = [
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
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_purchase_cost(self):
        cost = self.cleaned_data.get("purchase_cost")
        if cost is not None and cost < 0:
            raise forms.ValidationError("Purchase cost cannot be negative.")
        return cost
