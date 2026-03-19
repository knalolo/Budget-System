"""Payment release commands."""
from __future__ import annotations

import os

import click

from cli.client import get_client
from cli.formatters import (
    format_currency,
    print_detail,
    print_success,
    print_table,
)

_PR_LIST_COLUMNS = [
    ("ID", "id"),
    ("Number", "request_number"),
    ("Vendor", "vendor"),
    ("Amount", "total_price"),
    ("Currency", "currency"),
    ("PO Number", "po_number"),
    ("Status", "status"),
    ("Created", "created_at"),
]


@click.group(name="payment-releases")
def payment_releases_group() -> None:
    """Manage payment releases."""


@payment_releases_group.command("list")
@click.option("--status", default=None, help="Filter by status")
@click.option("--project", default=None, help="Filter by project ID")
def pr_list(status: str | None, project: str | None) -> None:
    """List payment releases."""
    client = get_client()
    params: dict = {}
    if status:
        params["status"] = status
    if project:
        params["project"] = project
    response = client.get("/api/v1/payment-releases/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No payment releases found.")
        return
    rows = [
        {**r, "total_price": format_currency(r.get("total_price"), r.get("currency", ""))}
        for r in items
    ]
    print_table(rows, _PR_LIST_COLUMNS, title="Payment Releases")


@payment_releases_group.command("create")
def pr_create() -> None:
    """Interactively create a new payment release."""
    client = get_client()

    proj_resp = client.get("/api/v1/projects/")
    cat_resp = client.get("/api/v1/expense-categories/")
    if not proj_resp.is_success or not cat_resp.is_success:
        raise SystemExit(1)

    projects = proj_resp.json().get("results", proj_resp.json())
    categories = cat_resp.json().get("results", cat_resp.json())

    if projects:
        click.echo("Projects:")
        for p in projects:
            click.echo(f"  [{p['id']}] {p['mc_number']} - {p['name']}")
    if categories:
        click.echo("Expense categories:")
        for c in categories:
            click.echo(f"  [{c['id']}] {c['name']}")

    project_id = click.prompt("Project ID", type=int)
    expense_category_id = click.prompt("Expense Category ID", type=int)
    purchase_request_id = click.prompt("Linked Purchase Request ID (0 to skip)", type=int, default=0)
    description = click.prompt("Description")
    vendor = click.prompt("Vendor")
    currency = click.prompt("Currency", default="SGD", type=click.Choice(["SGD", "USD", "EUR"]))
    total_price = click.prompt("Total Price", type=float)
    justification = click.prompt("Justification")
    po_number = click.prompt("PO Number (or N/A)")
    target_payment = click.prompt("Target Payment (e.g. 2025-Q1)")

    payload: dict = {
        "project": project_id,
        "expense_category": expense_category_id,
        "description": description,
        "vendor": vendor,
        "currency": currency,
        "total_price": str(total_price),
        "justification": justification,
        "po_number": po_number,
        "target_payment": target_payment,
    }
    if purchase_request_id:
        payload["purchase_request"] = purchase_request_id

    response = client.post("/api/v1/payment-releases/", data=payload)
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Payment release created: {result.get('request_number', result.get('id'))}")
    _show_detail(result)


@payment_releases_group.command("show")
@click.argument("release_id", type=int)
def pr_show(release_id: int) -> None:
    """Show detail for a payment release."""
    client = get_client()
    response = client.get(f"/api/v1/payment-releases/{release_id}/")
    if not response.is_success:
        raise SystemExit(1)
    _show_detail(response.json())


@payment_releases_group.command("submit")
@click.argument("release_id", type=int)
def pr_submit(release_id: int) -> None:
    """Submit a draft payment release for approval."""
    client = get_client()
    response = client.post(f"/api/v1/payment-releases/{release_id}/submit/")
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Payment release {release_id} submitted.")


@payment_releases_group.command("approve")
@click.argument("release_id", type=int)
@click.option("--comment", default="", help="Optional approval comment")
def pr_approve(release_id: int, comment: str) -> None:
    """Approve a payment release."""
    client = get_client()
    response = client.post(
        f"/api/v1/payment-releases/{release_id}/approve/", data={"comment": comment}
    )
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Payment release {release_id} approved.")


@payment_releases_group.command("reject")
@click.argument("release_id", type=int)
@click.option("--comment", default="", help="Rejection reason")
def pr_reject(release_id: int, comment: str) -> None:
    """Reject a payment release."""
    if not comment:
        comment = click.prompt("Rejection reason")
    client = get_client()
    response = client.post(
        f"/api/v1/payment-releases/{release_id}/reject/", data={"comment": comment}
    )
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Payment release {release_id} rejected.")


@payment_releases_group.command("upload")
@click.argument("release_id", type=int)
@click.argument("file_path", type=click.Path(exists=True, readable=True))
@click.option(
    "--file-type",
    default="invoice",
    type=click.Choice(["quote", "invoice", "po", "other"]),
    help="Type of attachment",
)
def pr_upload(release_id: int, file_path: str, file_type: str) -> None:
    """Upload a file attachment to a payment release."""
    client = get_client()
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        with click.progressbar(length=os.path.getsize(file_path), label=f"Uploading {filename}") as bar:
            content = fh.read()
            bar.update(len(content))
    with open(file_path, "rb") as fh:
        response = client.post(
            f"/api/v1/payment-releases/{release_id}/upload/",
            data={"file_type": file_type},
            files={"file": (filename, fh)},
        )
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"File '{filename}' uploaded to payment release {release_id}.")


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
            "PO Number": data.get("po_number", ""),
            "Description": data.get("description", ""),
            "Justification": data.get("justification", ""),
            "Target Payment": data.get("target_payment", ""),
            "Project": data.get("project", ""),
            "Category": data.get("expense_category", ""),
            "Created": data.get("created_at", ""),
        },
        title="Payment Release Detail",
    )
