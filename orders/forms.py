"""Forms for the orders app."""

from datetime import date, datetime

from django import forms

from .models import PurchaseRequest


class PurchaseRequestForm(forms.ModelForm):
    """Form for creating and editing a PurchaseRequest."""

    target_payment = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2 border",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = PurchaseRequest
        fields = [
            "expense_category",
            "project",
            "description",
            "vendor",
            "currency",
            "ordered_quantity",
            "total_price",
            "justification",
            "po_required",
            "target_payment",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "justification": forms.Textarea(attrs={"rows": 4}),
            "expense_category": forms.Select(),
            "project": forms.Select(),
            "currency": forms.Select(),
            "ordered_quantity": forms.NumberInput(attrs={"min": 1}),
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

    def clean_ordered_quantity(self):
        ordered_quantity = self.cleaned_data.get("ordered_quantity")
        if ordered_quantity is not None and ordered_quantity <= 0:
            raise forms.ValidationError("Ordered quantity must be at least 1.")
        return ordered_quantity

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
