"""Business logic and CSV export services for the assets app."""

import csv
import io

from django.http import HttpResponse

from .models import AssetItem, AssetRegistration

# ---------------------------------------------------------------------------
# AssetTiger CSV column headers (must match their import format exactly)
# ---------------------------------------------------------------------------

ASSETTIGER_HEADERS = [
    "Asset Name",
    "Asset Tag",
    "Category",
    "Serial Number",
    "Purchase Date",
    "Purchase Cost",
    "Supplier",
    "Location",
    "Department",
    "Assigned To",
    "Notes",
]

_CSV_FILENAME_TEMPLATE = "assettiger_export_{pk}.csv"
_TEMPLATE_FILENAME = "assettiger_import_template.csv"


def _build_csv_content(items: list[AssetItem]) -> str:
    """Return CSV string for the given list of AssetItem objects."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ASSETTIGER_HEADERS)
    for item in items:
        writer.writerow([
            item.asset_name,
            item.asset_tag,
            item.category,
            item.serial_number,
            item.purchase_date.isoformat() if item.purchase_date else "",
            str(item.purchase_cost) if item.purchase_cost is not None else "",
            item.supplier,
            item.location,
            item.department,
            item.assigned_to,
            item.notes,
        ])
    return buffer.getvalue()


def export_csv(registration: AssetRegistration) -> HttpResponse:
    """Generate and return an HttpResponse containing the AssetTiger CSV.

    Also marks the registration status as 'exported'.
    """
    items = list(registration.items.all())
    csv_content = _build_csv_content(items)

    filename = _CSV_FILENAME_TEMPLATE.format(pk=registration.pk)
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # Transition status to exported
    if registration.status in ("draft", "pending_export"):
        registration.status = "exported"
        registration.save(update_fields=["status", "updated_at"])

    return response


def get_csv_template() -> HttpResponse:
    """Return an empty CSV with just the AssetTiger header row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ASSETTIGER_HEADERS)
    csv_content = buffer.getvalue()

    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{_TEMPLATE_FILENAME}"'
    return response


def mark_imported(registration: AssetRegistration) -> AssetRegistration:
    """Mark a registration as imported in AssetTiger.

    Returns a new instance reflecting the updated state (immutable pattern).
    """
    registration.status = "imported"
    registration.save(update_fields=["status", "updated_at"])
    return registration
