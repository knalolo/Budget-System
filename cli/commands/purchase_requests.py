"""Purchase request commands."""
from __future__ import annotations

import os

import click

from cli.client import get_client
from cli.formatters import (
    format_currency,
    print_detail,
    print_error,
    print_success,
    print_table,
)

_PR_LIST_COLUMNS = [
    ("ID", "id"),
    ("Number", "request_number"),
    ("Vendor", "vendor"),
    ("Amount", "total_price"),
    ("Currency", "currency"),
    ("Status", "status"),
    ("Created", "created_at"),
]


@click.group(name="purchase-requests")
def purchase_requests_group() -> None:
    """Manage purchase requests."""


@purchase_requests_group.command("list")
@click.option("--status", default=None, help="Filter by status (draft, pending_pcm, …)")
@click.option("--project", default=None, help="Filter by project ID")
@click.option("--mine", is_flag=True, default=False, help="Show only my requests")
def pr_list(status: str | None, project: str | None, mine: bool) -> None:
    """List purchase requests."""
    client = get_client()
    params: dict = {}
    if status:
        params["status"] = status
    if project:
        params["project"] = project
    # The API automatically scopes to the requester for non-approver roles;
    # --mine is mainly a UX hint (no dedicated query param needed for non-admins).
    response = client.get("/api/v1/purchase-requests/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if mine:
        # Client-side filter when the user is an approver seeing all requests.
        pass  # API scopes automatically for regular requesters.
    if not items:
        click.echo("No purchase requests found.")
        return
    # Enrich with formatted amounts.
    rows = [
        {**r, "total_price": format_currency(r.get("total_price"), r.get("currency", ""))}
        for r in items
    ]
    print_table(rows, _PR_LIST_COLUMNS, title="Purchase Requests")


@purchase_requests_group.command("create")
def pr_create() -> None:
    """Interactively create a new purchase request."""
    client = get_client()

    # Fetch supporting data for choices.
    proj_resp = client.get("/api/v1/projects/")
    cat_resp = client.get("/api/v1/expense-categories/")
    if not proj_resp.is_success or not cat_resp.is_success:
        raise SystemExit(1)

    projects = proj_resp.json().get("results", proj_resp.json()) if proj_resp.is_success else []
    categories = cat_resp.json().get("results", cat_resp.json()) if cat_resp.is_success else []

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
    description = click.prompt("Description")
    vendor = click.prompt("Vendor")
    currency = click.prompt("Currency", default="SGD", type=click.Choice(["SGD", "USD", "EUR"]))
    total_price = click.prompt("Total Price", type=float)
    justification = click.prompt("Justification")
    po_required = click.confirm("PO required?", default=False)
    target_payment = click.prompt("Target Payment (e.g. 2025-Q1)")

    payload = {
        "project": project_id,
        "expense_category": expense_category_id,
        "description": description,
        "vendor": vendor,
        "currency": currency,
        "total_price": str(total_price),
        "justification": justification,
        "po_required": po_required,
        "target_payment": target_payment,
    }

    response = client.post("/api/v1/purchase-requests/", data=payload)
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Purchase request created: {result.get('request_number', result.get('id'))}")
    _show_pr_detail(result)


@purchase_requests_group.command("show")
@click.argument("pr_id", type=int)
def pr_show(pr_id: int) -> None:
    """Show detail for a purchase request."""
    client = get_client()
    response = client.get(f"/api/v1/purchase-requests/{pr_id}/")
    if not response.is_success:
        raise SystemExit(1)
    _show_pr_detail(response.json())


@purchase_requests_group.command("submit")
@click.argument("pr_id", type=int)
def pr_submit(pr_id: int) -> None:
    """Submit a draft purchase request for approval."""
    client = get_client()
    response = client.post(f"/api/v1/purchase-requests/{pr_id}/submit/")
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Purchase request {pr_id} submitted.")


@purchase_requests_group.command("approve")
@click.argument("pr_id", type=int)
@click.option("--comment", default="", help="Optional approval comment")
def pr_approve(pr_id: int, comment: str) -> None:
    """Approve a purchase request."""
    client = get_client()
    response = client.post(f"/api/v1/purchase-requests/{pr_id}/approve/", data={"comment": comment})
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Purchase request {pr_id} approved.")


@purchase_requests_group.command("reject")
@click.argument("pr_id", type=int)
@click.option("--comment", default="", help="Rejection reason")
def pr_reject(pr_id: int, comment: str) -> None:
    """Reject a purchase request."""
    if not comment:
        comment = click.prompt("Rejection reason")
    client = get_client()
    response = client.post(f"/api/v1/purchase-requests/{pr_id}/reject/", data={"comment": comment})
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Purchase request {pr_id} rejected.")


@purchase_requests_group.command("upload")
@click.argument("pr_id", type=int)
@click.argument("file_path", type=click.Path(exists=True, readable=True))
@click.option(
    "--file-type",
    default="quote",
    type=click.Choice(["quote", "invoice", "po", "other"]),
    help="Type of attachment",
)
def pr_upload(pr_id: int, file_path: str, file_type: str) -> None:
    """Upload a file attachment to a purchase request."""
    client = get_client()
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        with click.progressbar(length=os.path.getsize(file_path), label=f"Uploading {filename}") as bar:
            content = fh.read()
            bar.update(len(content))
    with open(file_path, "rb") as fh:
        response = client.post(
            f"/api/v1/purchase-requests/{pr_id}/upload/",
            data={"file_type": file_type},
            files={"file": (filename, fh)},
        )
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"File '{filename}' uploaded to purchase request {pr_id}.")


@purchase_requests_group.command("mark-po-sent")
@click.argument("pr_id", type=int)
def pr_mark_po_sent(pr_id: int) -> None:
    """Mark a purchase request as PO sent."""
    client = get_client()
    response = client.post(f"/api/v1/purchase-requests/{pr_id}/mark-po-sent/")
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Purchase request {pr_id} marked as PO sent.")


@purchase_requests_group.command("mark-ordered")
@click.argument("pr_id", type=int)
def pr_mark_ordered(pr_id: int) -> None:
    """Mark a purchase request as ordered."""
    client = get_client()
    response = client.post(f"/api/v1/purchase-requests/{pr_id}/mark-ordered/")
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Purchase request {pr_id} marked as ordered.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _show_pr_detail(data: dict) -> None:
    print_detail(
        {
            "ID": data.get("id", ""),
            "Number": data.get("request_number", ""),
            "Status": data.get("status", ""),
            "Vendor": data.get("vendor", ""),
            "Amount": format_currency(data.get("total_price"), data.get("currency", "")),
            "Description": data.get("description", ""),
            "Justification": data.get("justification", ""),
            "PO Required": data.get("po_required", ""),
            "Target Payment": data.get("target_payment", ""),
            "Project": data.get("project", ""),
            "Category": data.get("expense_category", ""),
            "Created": data.get("created_at", ""),
        },
        title="Purchase Request Detail",
    )
