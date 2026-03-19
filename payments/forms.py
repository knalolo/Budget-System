"""Forms for the payments app."""

from django import forms

from .models import PaymentRelease

PO_NUMBER_NA = "N/A"


class PaymentReleaseForm(forms.ModelForm):
    """Form for creating and editing a PaymentRelease."""

    class Meta:
        model = PaymentRelease
        fields = [
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "total_price",
            "justification",
            "po_number",
            "target_payment",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "justification": forms.Textarea(attrs={"rows": 4}),
            "expense_category": forms.Select(),
            "project": forms.Select(),
            "currency": forms.Select(),
            "po_number": forms.TextInput(attrs={"placeholder": "N/A or PO-XXXX"}),
            "target_payment": forms.TextInput(attrs={"placeholder": "e.g. 2026-04-01"}),
        }

    def clean_total_price(self):
        total_price = self.cleaned_data.get("total_price")
        if total_price is not None and total_price <= 0:
            raise forms.ValidationError("Total price must be greater than zero.")
        return total_price

    def clean_po_number(self):
        value = self.cleaned_data.get("po_number", "").strip()
        if not value:
            raise forms.ValidationError(
                "PO number is required. Enter 'N/A' if not applicable."
            )
        return value
