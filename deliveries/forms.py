"""Forms for the deliveries app."""

from django import forms

from .models import DeliverySubmission


class DeliverySubmissionForm(forms.ModelForm):
    """Form for creating a DeliverySubmission.

    File upload is handled separately via the delivery_submission_upload view.
    """

    class Meta:
        model = DeliverySubmission
        fields = ["vendor", "currency", "total_price"]
        widgets = {
            "vendor": forms.TextInput(attrs={"placeholder": "Vendor name"}),
            "currency": forms.Select(),
            "total_price": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}
            ),
        }

    def clean_total_price(self):
        total_price = self.cleaned_data.get("total_price")
        if total_price is not None and total_price <= 0:
            raise forms.ValidationError("Total price must be greater than zero.")
        return total_price
