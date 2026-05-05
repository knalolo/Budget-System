"""Dataset export helpers for purchase requests."""

from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal

from django.db.models import Prefetch, Sum
from django.http import HttpResponse

from core.services.exchange_rate_service import convert_amount_to_sgd

from .models import PurchaseRequest, PurchaseRequestLineItem

logger = logging.getLogger(__name__)

DATASET_HEADERS = [
    "Request No.",
    "Requester",
    "Submitted Date",
    "Last Updated",
    "Project",
    "MC Number",
    "Expense Category",
    "Vendor",
    "Product",
    "Currency",
    "Unit Price",
    "Quantity Ordered",
    "Quantity Delivered",
    "Outstanding Quantity",
    "Line Total",
    "Line Total in SGD",
    "PO Number",
    "Target Payment Date",
    "Goods Recieve Status",
    "Payment Release Status",
    "Workflow Stage",
    "Workflow Completed",
]

SAP_RECONCILIATION_HEADERS = [
    "Request No.",
    "Ledger",
    "Company Code",
    "Fiscal Year",
    "G/L Account",
    "G/L Account: Long Text",
    "Document Number",
    "Document Type",
    "Document Date",
    "Posting Date",
    "Company Code Currency Key",
    "Company Code Currency Value",
    "Text",
    "Purchasing Document",
]

_DATASET_CSV_FILENAME = "procurement_dataset_export.csv"
_SAP_RECONCILIATION_CSV_FILENAME = "procurement_sap_reconciliation_export.csv"


def _safe_convert_line_total_to_sgd(amount: Decimal, currency: str) -> str:
    """Return SGD-converted string for *amount*, leaving blank if FX lookup fails."""
    try:
        converted = convert_amount_to_sgd(amount, currency)
    except RuntimeError as exc:
        logger.warning(
            "Could not convert %s %s to SGD for dataset export: %s",
            currency,
            amount,
            exc,
        )
        return ""
    return f"{converted:.2f}"


def _requester_display_name(purchase_request: PurchaseRequest) -> str:
    requester = purchase_request.requester
    return requester.get_full_name() or requester.username


def _po_number_for_export(purchase_request: PurchaseRequest) -> str:
    latest_payment = purchase_request.latest_payment_release
    if latest_payment is None:
        return ""
    return latest_payment.po_number


def _document_date_for_export(purchase_request: PurchaseRequest) -> str:
    return purchase_request.created_at.strftime("%Y-%m-%d")


def _fiscal_year_for_export(purchase_request: PurchaseRequest) -> int:
    target_payment = purchase_request.target_payment
    if target_payment:
        if hasattr(target_payment, "year"):
            return target_payment.year
        return int(str(target_payment)[:4])
    return purchase_request.created_at.year


def _sap_text_for_export(
    purchase_request: PurchaseRequest,
    line_item: PurchaseRequestLineItem,
) -> str:
    parts = [
        purchase_request.vendor,
        line_item.product,
        purchase_request.workflow_number,
        purchase_request.project.mc_number,
    ]
    return " - ".join(part for part in parts if part)


def _line_item_rows(purchase_request: PurchaseRequest):
    line_items = list(purchase_request.line_items.all())
    if line_items:
        return line_items

    fallback = PurchaseRequestLineItem(
        purchase_request=purchase_request,
        sequence=1,
        product=purchase_request.description,
        quantity=purchase_request.ordered_quantity,
        unit_price=purchase_request.unit_price,
        total_price=purchase_request.total_price,
        currency=purchase_request.currency,
    )
    fallback.pk = None
    return [fallback]


def _delivered_quantity_for_line_item(line_item: PurchaseRequestLineItem) -> int:
    if line_item.pk is None:
        return line_item.purchase_request.delivered_quantity

    delivered_total = line_item.delivery_line_items.aggregate(total=Sum("delivered_quantity"))["total"]
    return int(delivered_total or 0)


def _build_csv_content(purchase_requests) -> str:
    """Return CSV content for the given iterable of purchase requests."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(DATASET_HEADERS)

    for purchase_request in purchase_requests:
        for line_item in _line_item_rows(purchase_request):
            delivered_quantity = min(
                _delivered_quantity_for_line_item(line_item),
                line_item.quantity,
            )
            outstanding_quantity = max(line_item.quantity - delivered_quantity, 0)
            line_total = line_item.total_price

            writer.writerow(
                [
                    purchase_request.workflow_number,
                    _requester_display_name(purchase_request),
                    purchase_request.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    purchase_request.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    purchase_request.project.name,
                    purchase_request.project.mc_number,
                    purchase_request.expense_category.name,
                    purchase_request.vendor,
                    line_item.product,
                    line_item.currency,
                    f"{line_item.unit_price:.2f}",
                    line_item.quantity,
                    delivered_quantity,
                    outstanding_quantity,
                    f"{line_total:.2f}",
                    _safe_convert_line_total_to_sgd(line_total, line_item.currency),
                    _po_number_for_export(purchase_request),
                    purchase_request.target_payment,
                    purchase_request.goods_stage_display,
                    purchase_request.payment_stage_display,
                    purchase_request.workflow_stage_display,
                    "Yes" if purchase_request.workflow_completed else "No",
                ]
            )

    return buffer.getvalue()


def _build_sap_reconciliation_csv_content(purchase_requests) -> str:
    """Return SAP-style reconciliation CSV content for the provided requests."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(SAP_RECONCILIATION_HEADERS)

    for purchase_request in purchase_requests:
        for line_item in _line_item_rows(purchase_request):
            line_total = line_item.total_price
            writer.writerow(
                [
                    purchase_request.workflow_number,
                    "",
                    "",
                    _fiscal_year_for_export(purchase_request),
                    "",
                    purchase_request.expense_category.name,
                    "",
                    "",
                    _document_date_for_export(purchase_request),
                    "",
                    "SGD",
                    _safe_convert_line_total_to_sgd(line_total, line_item.currency),
                    _sap_text_for_export(purchase_request, line_item),
                    _po_number_for_export(purchase_request),
                ]
            )

    return buffer.getvalue()


def export_purchase_request_dataset(queryset) -> HttpResponse:
    """Return a CSV export response for the provided purchase request queryset."""
    prefetched_queryset = queryset.select_related(
        "requester",
        "project",
        "expense_category",
    ).prefetch_related(
        Prefetch(
            "line_items",
            queryset=PurchaseRequestLineItem.objects.all().prefetch_related(
                "delivery_line_items"
            ),
        ),
        "payment_releases",
        "delivery_submissions",
    )

    csv_content = _build_csv_content(prefetched_queryset)
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{_DATASET_CSV_FILENAME}"'
    return response


def export_purchase_request_sap_reconciliation(queryset) -> HttpResponse:
    """Return a SAP-style reconciliation CSV export response."""
    prefetched_queryset = queryset.select_related(
        "requester",
        "project",
        "expense_category",
    ).prefetch_related(
        Prefetch(
            "line_items",
            queryset=PurchaseRequestLineItem.objects.all().prefetch_related(
                "delivery_line_items"
            ),
        ),
        "payment_releases",
        "delivery_submissions",
    )

    csv_content = _build_sap_reconciliation_csv_content(prefetched_queryset)
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{_SAP_RECONCILIATION_CSV_FILENAME}"'
    )
    return response
