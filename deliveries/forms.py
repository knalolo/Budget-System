"""Forms for the deliveries app."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP

from django import forms

from .models import DeliverySubmission, DeliverySubmissionLineItem


class DeliverySubmissionForm(forms.ModelForm):
    """Form for creating a DeliverySubmission."""

    currency = forms.ChoiceField(
        required=False,
        choices=DeliverySubmission._meta.get_field("currency").choices,
        widget=forms.HiddenInput(),
    )
    delivered_quantity = forms.IntegerField(required=False, widget=forms.HiddenInput())
    total_price = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.HiddenInput(),
    )
    status = forms.CharField(required=False, widget=forms.HiddenInput())
    line_items_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = DeliverySubmission
        fields = ["vendor", "currency", "delivered_quantity", "total_price", "status", "notes"]
        widgets = {
            "vendor": forms.TextInput(attrs={"placeholder": "Vendor name"}),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional notes about shortages or follow-up.",
                }
            ),
        }

    def __init__(self, *args, source_purchase_request=None, **kwargs):
        self.source_purchase_request = source_purchase_request
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["line_items_json"] = json.dumps(self._initial_line_items())
            if source_purchase_request is not None:
                self.initial["vendor"] = source_purchase_request.vendor
        self.parsed_line_items: list[dict] = []

    def clean(self):
        cleaned_data = super().clean()
        line_items_raw = (cleaned_data.get("line_items_json") or "").strip()
        if line_items_raw:
            self.parsed_line_items = self._parse_line_items(line_items_raw)
            self._apply_line_item_totals(cleaned_data)
        return cleaned_data

    def save_line_items(self, submission: DeliverySubmission) -> None:
        """Persist parsed line items for the given delivery submission."""
        submission.line_items.all().delete()
        if not self.parsed_line_items:
            return

        DeliverySubmissionLineItem.objects.bulk_create(
            [
                DeliverySubmissionLineItem(
                    delivery_submission=submission,
                    purchase_request_line_item_id=item.get("purchase_request_line_item_id"),
                    sequence=item["sequence"],
                    product=item["product"],
                    ordered_quantity=item["ordered_quantity"],
                    delivered_quantity=item["delivered_quantity"],
                    unit_price=item["unit_price"],
                    total_price=item["total_price"],
                    currency=item["currency"],
                    status=item["status"],
                )
                for item in self.parsed_line_items
            ]
        )

    def _initial_line_items(self) -> list[dict]:
        if self.instance and self.instance.pk:
            existing_line_items = list(self.instance.line_items.all())
            if existing_line_items:
                return [
                    {
                        "sequence": line_item.sequence,
                        "product": line_item.product,
                        "ordered_quantity": line_item.ordered_quantity,
                        "delivered_quantity": line_item.delivered_quantity,
                        "unit_price": f"{line_item.unit_price:.2f}",
                        "total_price": f"{line_item.total_price:.2f}",
                        "display_total_price": f"{line_item.total_price:.2f}",
                        "currency": line_item.currency,
                        "status": line_item.status,
                        "purchase_request_line_item_id": line_item.purchase_request_line_item_id or "",
                    }
                    for line_item in existing_line_items
                ]

        if self.source_purchase_request is None:
            return [
                {
                    "sequence": 1,
                    "product": "",
                    "ordered_quantity": 1,
                    "delivered_quantity": 1,
                    "unit_price": "",
                    "total_price": "",
                    "currency": "SGD",
                    "status": "fully_delivered",
                    "purchase_request_line_item_id": "",
                }
            ]

        purchase_request = self.source_purchase_request
        existing_items = list(purchase_request.line_items.all())
        if not existing_items:
            return [
                {
                    "sequence": 1,
                    "product": purchase_request.description,
                    "ordered_quantity": purchase_request.remaining_quantity or purchase_request.ordered_quantity,
                    "delivered_quantity": purchase_request.remaining_quantity or purchase_request.ordered_quantity,
                    "unit_price": f"{purchase_request.unit_price:.2f}",
                    "total_price": f"{(purchase_request.unit_price * Decimal(purchase_request.remaining_quantity or purchase_request.ordered_quantity)):.2f}",
                    "currency": purchase_request.currency,
                    "status": "fully_delivered",
                    "purchase_request_line_item_id": "",
                }
            ]

        delivered_by_line_item = {}
        for line_item in purchase_request.delivery_submissions.prefetch_related("line_items").all():
            for delivery_line in line_item.line_items.all():
                key = delivery_line.purchase_request_line_item_id or delivery_line.sequence
                delivered_by_line_item[key] = delivered_by_line_item.get(key, 0) + delivery_line.delivered_quantity

        initial_rows: list[dict] = []
        for index, item in enumerate(existing_items, start=1):
            delivered_so_far = delivered_by_line_item.get(item.id, 0)
            remaining_quantity = max(item.quantity - delivered_so_far, 0)
            default_status = "fully_delivered" if remaining_quantity == item.quantity else "partially_delivered"
            initial_rows.append(
                {
                    "sequence": index,
                    "product": item.product,
                    "ordered_quantity": item.quantity,
                    "delivered_quantity": remaining_quantity,
                    "unit_price": f"{item.unit_price:.2f}",
                    "total_price": f"{(item.unit_price * Decimal(remaining_quantity)):.2f}",
                    "currency": item.currency,
                    "status": default_status,
                    "purchase_request_line_item_id": item.id,
                }
            )
        return initial_rows

    def _parse_line_items(self, raw_value: str) -> list[dict]:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Line items could not be parsed.") from exc

        if not isinstance(payload, list) or not payload:
            raise forms.ValidationError("At least one delivery line item is required.")

        parsed_items: list[dict] = []
        currencies: set[str] = set()

        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("Each delivery line item must be a valid object.")

            product = str(item.get("product", "")).strip()
            if not product:
                raise forms.ValidationError(f"Line {index}: Product is required.")

            ordered_quantity = self._parse_positive_int(
                item.get("ordered_quantity"),
                f"Line {index}: Ordered quantity must be at least 1.",
            )
            delivered_quantity = self._parse_positive_int(
                item.get("delivered_quantity"),
                f"Line {index}: Actual delivered quantity must be at least 1.",
            )
            if delivered_quantity > ordered_quantity:
                raise forms.ValidationError(
                    f"Line {index}: Actual delivered quantity cannot exceed ordered quantity."
                )

            unit_price = self._parse_positive_decimal(
                item.get("unit_price"),
                f"Line {index}: Unit price must be greater than zero.",
            )
            currency = str(item.get("currency", "")).strip().upper()
            valid_currencies = {choice for choice, _ in DeliverySubmission._meta.get_field("currency").choices}
            if currency not in valid_currencies:
                raise forms.ValidationError(f"Line {index}: Currency is invalid.")

            status = str(item.get("status", "")).strip()
            if status not in ("partially_delivered", "fully_delivered"):
                raise forms.ValidationError(
                    f"Line {index}: Delivery outcome must be Partially Delivered or Fully Delivered."
                )

            total_price = (Decimal(delivered_quantity) * unit_price).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            currencies.add(currency)
            parsed_items.append(
                {
                    "sequence": index,
                    "product": product,
                    "ordered_quantity": ordered_quantity,
                    "delivered_quantity": delivered_quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "currency": currency,
                    "status": status,
                    "purchase_request_line_item_id": item.get("purchase_request_line_item_id") or None,
                }
            )

        if len(currencies) > 1:
            raise forms.ValidationError("All line items in one goods receive record must use the same currency.")

        return parsed_items

    def _apply_line_item_totals(self, cleaned_data: dict) -> None:
        if not self.parsed_line_items:
            return

        cleaned_data["currency"] = self.parsed_line_items[0]["currency"]
        cleaned_data["delivered_quantity"] = sum(item["delivered_quantity"] for item in self.parsed_line_items)
        cleaned_data["total_price"] = sum(
            (item["total_price"] for item in self.parsed_line_items),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned_data["status"] = (
            "fully_delivered"
            if all(item["status"] == "fully_delivered" for item in self.parsed_line_items)
            else "partially_delivered"
        )

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
