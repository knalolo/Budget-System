"""Delivery submission commands."""
from __future__ import annotations

import os

import click

from cli.client import get_client
from cli.formatters import format_currency, print_detail, print_success, print_table

_DS_LIST_COLUMNS = [
    ("ID", "id"),
    ("Number", "request_number"),
    ("Vendor", "vendor"),
    ("Amount", "total_price"),
    ("Currency", "currency"),
    ("Status", "status"),
    ("Created", "created_at"),
]


@click.group(name="delivery-submissions")
def delivery_submissions_group() -> None:
    """Manage delivery submissions (DO/SO)."""


@delivery_submissions_group.command("list")
@click.option("--vendor", default=None, help="Filter by vendor name")
@click.option("--status", default=None, help="Filter by status")
def ds_list(vendor: str | None, status: str | None) -> None:
    """List delivery submissions."""
    client = get_client()
    params: dict = {}
    if vendor:
        params["vendor"] = vendor
    if status:
        params["status"] = status
    response = client.get("/api/v1/delivery-submissions/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No delivery submissions found.")
        return
    rows = [
        {**r, "total_price": format_currency(r.get("total_price"), r.get("currency", ""))}
        for r in items
    ]
    print_table(rows, _DS_LIST_COLUMNS, title="Delivery Submissions")


@delivery_submissions_group.command("create")
def ds_create() -> None:
    """Interactively create a new delivery submission."""
    client = get_client()

    # Optional PR link.
    pr_id_raw = click.prompt("Linked Purchase Request ID (0 to skip)", default="0")
    vendor = click.prompt("Vendor")
    currency = click.prompt("Currency", default="SGD", type=click.Choice(["SGD", "USD", "EUR"]))
    total_price = click.prompt("Total Price", type=float)

    payload: dict = {
        "vendor": vendor,
        "currency": currency,
        "total_price": str(total_price),
    }
    try:
        pr_id = int(pr_id_raw)
        if pr_id:
            payload["purchase_request"] = pr_id
    except ValueError:
        pass

    response = client.post("/api/v1/delivery-submissions/", data=payload)
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Delivery submission created: {result.get('request_number', result.get('id'))}")
    _show_detail(result)


@delivery_submissions_group.command("show")
@click.argument("submission_id", type=int)
def ds_show(submission_id: int) -> None:
    """Show detail for a delivery submission."""
    client = get_client()
    response = client.get(f"/api/v1/delivery-submissions/{submission_id}/")
    if not response.is_success:
        raise SystemExit(1)
    _show_detail(response.json())


@delivery_submissions_group.command("upload")
@click.argument("submission_id", type=int)
@click.argument("file_path", type=click.Path(exists=True, readable=True))
@click.option(
    "--file-type",
    default="other",
    type=click.Choice(["quote", "invoice", "po", "other"]),
    help="Type of attachment",
)
def ds_upload(submission_id: int, file_path: str, file_type: str) -> None:
    """Upload a file attachment to a delivery submission."""
    client = get_client()
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        with click.progressbar(length=os.path.getsize(file_path), label=f"Uploading {filename}") as bar:
            content = fh.read()
            bar.update(len(content))
    with open(file_path, "rb") as fh:
        response = client.post(
            f"/api/v1/delivery-submissions/{submission_id}/upload/",
            data={"file_type": file_type},
            files={"file": (filename, fh)},
        )
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"File '{filename}' uploaded to delivery submission {submission_id}.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _show_detail(data: dict) -> None:
    print_detail(
        {
            "ID": data.get("id", ""),
            "Number": data.get("request_number", ""),
            "Status": data.get("status", ""),
            "Vendor": data.get("vendor", ""),
            "Amount": format_currency(data.get("total_price"), data.get("currency", "")),
            "Linked PR": data.get("purchase_request", ""),
            "Created": data.get("created_at", ""),
        },
        title="Delivery Submission Detail",
    )
