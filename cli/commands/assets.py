"""Asset registration commands."""
from __future__ import annotations

import click

from cli.client import get_client
from cli.formatters import print_detail, print_error, print_success, print_table, print_warning

_ASSET_LIST_COLUMNS = [
    ("ID", "id"),
    ("Name", "name"),
    ("Tag", "asset_tag"),
    ("Category", "category"),
    ("Location", "location"),
    ("Status", "status"),
]

_ITEM_COLUMNS = [
    ("ID", "id"),
    ("Serial", "serial_number"),
    ("Description", "description"),
    ("Unit Price", "unit_price"),
    ("Currency", "currency"),
]


@click.group(name="assets")
def assets_group() -> None:
    """Manage asset registrations."""


@assets_group.command("list")
@click.option("--status", default=None, help="Filter by status")
@click.option("--category", default=None, help="Filter by category")
def asset_list(status: str | None, category: str | None) -> None:
    """List asset registrations."""
    client = get_client()
    params: dict = {}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    response = client.get("/api/v1/asset-registrations/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No asset registrations found.")
        return
    print_table(items, _ASSET_LIST_COLUMNS, title="Asset Registrations")


@assets_group.command("create")
def asset_create() -> None:
    """Interactively create a new asset registration."""
    client = get_client()

    name = click.prompt("Asset name")
    asset_tag = click.prompt("Asset tag", default="")
    category = click.prompt("Category", default="")
    location = click.prompt("Location", default="")
    purchase_date = click.prompt("Purchase date (YYYY-MM-DD)", default="")
    notes = click.prompt("Notes", default="")

    payload: dict = {"name": name}
    if asset_tag:
        payload["asset_tag"] = asset_tag
    if category:
        payload["category"] = category
    if location:
        payload["location"] = location
    if purchase_date:
        payload["purchase_date"] = purchase_date
    if notes:
        payload["notes"] = notes

    response = client.post("/api/v1/asset-registrations/", data=payload)
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Asset registration created: ID {result.get('id')}")
    _show_detail(result)


@assets_group.command("show")
@click.argument("asset_id", type=int)
def asset_show(asset_id: int) -> None:
    """Show detail for an asset registration."""
    client = get_client()
    response = client.get(f"/api/v1/asset-registrations/{asset_id}/")
    if not response.is_success:
        raise SystemExit(1)
    _show_detail(response.json())


@assets_group.command("add-item")
@click.argument("asset_id", type=int)
def asset_add_item(asset_id: int) -> None:
    """Interactively add an asset item to a registration."""
    client = get_client()

    serial_number = click.prompt("Serial number", default="")
    description = click.prompt("Description")
    unit_price = click.prompt("Unit price", type=float, default=0.0)
    currency = click.prompt("Currency", default="SGD", type=click.Choice(["SGD", "USD", "EUR"]))
    quantity = click.prompt("Quantity", type=int, default=1)

    payload: dict = {
        "description": description,
        "unit_price": str(unit_price),
        "currency": currency,
        "quantity": quantity,
    }
    if serial_number:
        payload["serial_number"] = serial_number

    response = client.post(f"/api/v1/asset-registrations/{asset_id}/add-item/", data=payload)
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Item added to asset registration {asset_id}.")


@assets_group.command("export-csv")
@click.argument("asset_id", type=int)
@click.option("--output", "-o", default=None, help="Output file path (default: asset_<id>.csv)")
def asset_export_csv(asset_id: int, output: str | None) -> None:
    """Download asset registration as CSV."""
    client = get_client()
    response = client.get(f"/api/v1/asset-registrations/{asset_id}/export-csv/")
    if not response.is_success:
        raise SystemExit(1)
    filename = output or f"asset_{asset_id}.csv"
    with open(filename, "wb") as fh:
        fh.write(response.content)
    print_success(f"CSV saved to: {filename}")


@assets_group.command("import-template")
@click.argument("file_path", type=click.Path(exists=True, readable=True))
def asset_import_template(file_path: str) -> None:
    """Import asset items from a CSV template (placeholder)."""
    print_warning(
        f"Import from '{file_path}' is not yet implemented on the server side. "
        "This command is a placeholder for future bulk-import functionality."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _show_detail(data: dict) -> None:
    items = data.pop("items", []) if isinstance(data, dict) else []
    print_detail(
        {
            "ID": data.get("id", ""),
            "Name": data.get("name", ""),
            "Asset Tag": data.get("asset_tag", ""),
            "Category": data.get("category", ""),
            "Location": data.get("location", ""),
            "Status": data.get("status", ""),
            "Purchase Date": data.get("purchase_date", ""),
            "Notes": data.get("notes", ""),
        },
        title="Asset Registration Detail",
    )
    if items:
        print_table(items, _ITEM_COLUMNS, title="Asset Items")
