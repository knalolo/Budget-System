"""Forms for the assets app."""

from django import forms

from payments.models import PaymentRelease

from .models import AssetItem, AssetRegistration


class AssetRegistrationForm(forms.ModelForm):
    """Form for the top-level AssetRegistration record."""

    payment_release = forms.ModelChoiceField(
        queryset=PaymentRelease.objects.filter(status="approved").order_by("-created_at"),
        required=False,
        empty_label="-- None (standalone registration) --",
        help_text="Optionally link this registration to an approved payment release.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_release"].label_from_instance = (
            lambda payment_release: f"{payment_release.request_number} - {payment_release.vendor}"
        )

    class Meta:
        model = AssetRegistration
        fields = ["payment_release", "notes"]
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
