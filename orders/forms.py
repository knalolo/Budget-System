"""Forms for the orders app."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.conf import settings

from .models import ExpenseCategory, Project, PurchaseRequest, PurchaseRequestLineItem


class PurchaseRequestForm(forms.ModelForm):
    """Form for creating and editing a PurchaseRequest."""

    purchase_type = forms.ChoiceField(
        choices=settings.PURCHASE_TYPE_CHOICES,
    )
    execution_mode = forms.ChoiceField(
        choices=settings.EXECUTION_MODE_CHOICES,
        widget=forms.RadioSelect,
    )
    description = forms.CharField(required=False, widget=forms.HiddenInput())
    currency = forms.ChoiceField(
        required=False,
        choices=PurchaseRequest._meta.get_field("currency").choices,
        widget=forms.HiddenInput(),
    )
    ordered_quantity = forms.IntegerField(required=False, widget=forms.HiddenInput())
    total_price = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.HiddenInput(),
    )
    line_items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    target_payment = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": (
                    "block w-full rounded-md border-gray-300 shadow-sm text-sm "
                    "focus:border-brand-500 focus:ring-brand-500 px-3 py-2 border"
                ),
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = PurchaseRequest
        fields = [
            "purchase_type",
            "execution_mode",
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
            "justification": forms.Textarea(attrs={"rows": 4}),
            "expense_category": forms.HiddenInput(),
            "project": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(is_active=True).order_by("mc_number")
        self.fields["expense_category"].queryset = ExpenseCategory.objects.filter(is_active=True).order_by("name")
        self.fields["expense_category"].required = False

        if self.instance and self.instance.pk:
            self.initial.setdefault("purchase_type", self.instance.purchase_type)
            self.initial.setdefault("execution_mode", self.instance.execution_mode)
            self.initial.setdefault("expense_category", self.instance.expense_category_id)
        else:
            self.initial.setdefault("execution_mode", settings.EXECUTION_MODE_DELIVERY_FIRST)
            default_expense_category = self._default_expense_category()
            if default_expense_category is not None:
                self.initial.setdefault("expense_category", default_expense_category.pk)

        target_payment = self.initial.get("target_payment")
        if isinstance(target_payment, str):
            self.initial["target_payment"] = self._parse_target_payment(target_payment)
        if not self.is_bound:
            self.initial["line_items_json"] = json.dumps(self._initial_line_items())
        self.parsed_line_items: list[dict] = []

    def clean_target_payment(self):
        target_payment = self.cleaned_data.get("target_payment")
        if isinstance(target_payment, date):
            return target_payment.isoformat()
        return target_payment

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("expense_category"):
            default_expense_category = self._default_expense_category()
            if default_expense_category is None:
                self.add_error(None, "At least one active expense category is required in the system configuration.")
            else:
                cleaned_data["expense_category"] = default_expense_category
        line_items_raw = (cleaned_data.get("line_items_json") or "").strip()
        if line_items_raw:
            self.parsed_line_items = self._parse_line_items(line_items_raw)
            self._apply_line_item_totals(cleaned_data)
        else:
            self.parsed_line_items = self._fallback_line_items(cleaned_data)
        return cleaned_data

    def save_line_items(self, purchase_request: PurchaseRequest) -> None:
        """Persist the parsed line items for the given purchase request."""
        purchase_request.line_items.all().delete()
        if not self.parsed_line_items:
            return

        PurchaseRequestLineItem.objects.bulk_create(
            [
                PurchaseRequestLineItem(
                    purchase_request=purchase_request,
                    sequence=item["sequence"],
                    product=item["product"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    total_price=item["total_price"],
                    currency=item["currency"],
                )
                for item in self.parsed_line_items
            ]
        )

    def _initial_line_items(self) -> list[dict]:
        if self.instance and self.instance.pk:
            existing_items = list(self.instance.line_items.all())
            if existing_items:
                return [
                    {
                        "sequence": item.sequence,
                        "product": item.product,
                        "quantity": item.quantity,
                        "unit_price": f"{item.unit_price:.2f}",
                        "total_price": f"{item.total_price:.2f}",
                        "currency": item.currency,
                    }
                    for item in existing_items
                ]

            return [
                {
                    "sequence": 1,
                    "product": self.instance.description,
                    "quantity": self.instance.ordered_quantity,
                    "unit_price": f"{self.instance.unit_price:.2f}",
                    "total_price": f"{self.instance.total_price:.2f}",
                    "currency": self.instance.currency,
                }
            ]

        return [
            {
                "sequence": 1,
                "product": "",
                "quantity": 1,
                "unit_price": "",
                "total_price": "",
                "currency": "SGD",
            }
        ]

    def _parse_line_items(self, raw_value: str) -> list[dict]:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Line items could not be parsed.") from exc

        if not isinstance(payload, list) or not payload:
            raise forms.ValidationError("At least one line item is required.")

        parsed_items: list[dict] = []
        currencies: set[str] = set()

        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("Each line item must be a valid object.")

            product = str(item.get("product", "")).strip()
            if not product:
                raise forms.ValidationError(f"Line {index}: Product is required.")

            quantity = self._parse_positive_int(item.get("quantity"), f"Line {index}: Quantity must be at least 1.")
            unit_price = self._parse_positive_decimal(
                item.get("unit_price"),
                f"Line {index}: Unit price must be greater than zero.",
            )
            currency = str(item.get("currency", "")).strip().upper()
            valid_currencies = {choice for choice, _ in PurchaseRequest._meta.get_field("currency").choices}
            if currency not in valid_currencies:
                raise forms.ValidationError(f"Line {index}: Currency is invalid.")

            total_price = (Decimal(quantity) * unit_price).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            currencies.add(currency)
            parsed_items.append(
                {
                    "sequence": index,
                    "product": product,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "currency": currency,
                }
            )

        if len(currencies) > 1:
            raise forms.ValidationError("All line items in one purchase request must use the same currency.")

        return parsed_items

    def _apply_line_item_totals(self, cleaned_data: dict) -> None:
        if not self.parsed_line_items:
            return

        total_quantity = sum(item["quantity"] for item in self.parsed_line_items)
        total_price = sum((item["total_price"] for item in self.parsed_line_items), Decimal("0.00"))
        currency = self.parsed_line_items[0]["currency"]
        description_summary = "; ".join(item["product"] for item in self.parsed_line_items)

        cleaned_data["ordered_quantity"] = total_quantity
        cleaned_data["total_price"] = total_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned_data["currency"] = currency
        cleaned_data["description"] = description_summary

    def _fallback_line_items(self, cleaned_data: dict) -> list[dict]:
        description = (cleaned_data.get("description") or "").strip()
        ordered_quantity = cleaned_data.get("ordered_quantity")
        total_price = cleaned_data.get("total_price")
        currency = cleaned_data.get("currency")

        if not description or not ordered_quantity or not total_price or not currency:
            return []

        unit_price = (Decimal(total_price) / Decimal(ordered_quantity)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return [
            {
                "sequence": 1,
                "product": description,
                "quantity": ordered_quantity,
                "unit_price": unit_price,
                "total_price": Decimal(total_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "currency": currency,
            }
        ]

    @staticmethod
    def _parse_positive_int(value, error_message: str) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError(error_message) from exc
        if parsed <= 0:
            raise forms.ValidationError(error_message)
        return parsed

    @staticmethod
    def _parse_positive_decimal(value, error_message: str) -> Decimal:
        try:
            parsed = Decimal(str(value).strip())
        except Exception as exc:  # noqa: BLE001
            raise forms.ValidationError(error_message) from exc
        if parsed <= 0:
            raise forms.ValidationError(error_message)
        return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

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

    @staticmethod
    def _default_expense_category():
        return ExpenseCategory.objects.filter(is_active=True).order_by("name").first()
