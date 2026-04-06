"""Forms for the deliveries app."""

from django import forms

from .models import DeliverySubmission


class DeliverySubmissionForm(forms.ModelForm):
    """Form for creating a DeliverySubmission.

    File upload is handled separately via the delivery_submission_upload view.
    """

    class Meta:
        model = DeliverySubmission
        fields = ["vendor", "currency", "delivered_quantity", "total_price", "status", "notes"]
        widgets = {
            "vendor": forms.TextInput(attrs={"placeholder": "Vendor name"}),
            "currency": forms.Select(),
            "delivered_quantity": forms.NumberInput(
                attrs={"min": "1", "step": "1", "placeholder": "1"}
            ),
            "total_price": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
            "status": forms.Select(),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional notes about partial delivery, shortages, or follow-up.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            ("partially_delivered", "Partially Delivered"),
            ("fully_delivered", "Fully Delivered"),
            ("short_closed", "Short Closed"),
        ]

    def clean_total_price(self):
        total_price = self.cleaned_data.get("total_price")
        if total_price is not None and total_price <= 0:
            raise forms.ValidationError("Total price must be greater than zero.")
        return total_price

    def clean_delivered_quantity(self):
        delivered_quantity = self.cleaned_data.get("delivered_quantity")
        if delivered_quantity is not None and delivered_quantity <= 0:
            raise forms.ValidationError("Delivered quantity must be at least 1.")
        return delivered_quantity
