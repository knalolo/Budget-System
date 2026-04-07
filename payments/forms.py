"""Forms for the payments app."""

from datetime import date, datetime

from django import forms

from .models import PaymentRelease

PO_NUMBER_NA = "N/A"


class PaymentReleaseForm(forms.ModelForm):
    """Form for creating and editing a PaymentRelease."""

    target_payment = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = PaymentRelease
        fields = [
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "payment_type",
            "payment_quantity",
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
            "payment_type": forms.Select(),
            "payment_quantity": forms.NumberInput(attrs={"min": 1}),
            "po_number": forms.TextInput(attrs={"placeholder": "N/A or PO-XXXX"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        target_payment = self.initial.get("target_payment")
        if isinstance(target_payment, str):
            self.initial["target_payment"] = self._parse_target_payment(target_payment)

    def clean_target_payment(self):
        target_payment = self.cleaned_data.get("target_payment")
        if isinstance(target_payment, date):
            return target_payment.isoformat()
        return target_payment

    def clean_total_price(self):
        total_price = self.cleaned_data.get("total_price")
        if total_price is not None and total_price <= 0:
            raise forms.ValidationError("Total price must be greater than zero.")
        return total_price

    def clean_payment_quantity(self):
        payment_quantity = self.cleaned_data.get("payment_quantity")
        if payment_quantity is not None and payment_quantity <= 0:
            raise forms.ValidationError("Payment quantity must be at least 1.")
        return payment_quantity

    def clean_po_number(self):
        value = self.cleaned_data.get("po_number", "").strip()
        if not value:
            raise forms.ValidationError(
                "PO number is required. Enter 'N/A' if not applicable."
            )
        return value

    @staticmethod
    def _parse_target_payment(raw_value: str):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return raw_value
        for input_format in ("%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(raw_value, input_format).date()
            except ValueError:
                continue
        return raw_value
