"""Forms for the orders app."""

from django import forms

from .models import PurchaseRequest


class PurchaseRequestForm(forms.ModelForm):
    """Form for creating and editing a PurchaseRequest."""

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
