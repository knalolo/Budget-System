"""Admin commands: config, users, expense-categories, logs."""
from __future__ import annotations

import click

from cli.client import get_client
from cli.formatters import print_detail, print_success, print_table

# ---------------------------------------------------------------------------
# config group
# ---------------------------------------------------------------------------


@click.group(name="config")
def config_group() -> None:
    """Manage system configuration."""


@config_group.command("list")
def config_list() -> None:
    """Show all system configuration entries."""
    client = get_client()
    response = client.get("/api/v1/config/")
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No configuration entries found.")
        return
    print_table(
        items,
        [("Key", "key"), ("Value", "value"), ("Description", "description")],
        title="System Configuration",
    )


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a system configuration value."""
    client = get_client()
    # Try PATCH first; if the endpoint uses a keyed URL, adapt as needed.
    response = client.patch(f"/api/v1/config/{key}/", data={"value": value})
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"Config '{key}' updated to '{value}'.")


@config_group.command("thresholds")
def config_thresholds() -> None:
    """Show PO approval thresholds."""
    client = get_client()
    response = client.get("/api/v1/config/")
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    threshold_keys = {"po_threshold_sgd", "po_threshold_usd", "po_threshold_eur"}
    thresholds = [i for i in items if i.get("key") in threshold_keys]
    if not thresholds:
        click.echo("No PO threshold configuration found.")
        return
    print_table(
        thresholds,
        [("Key", "key"), ("Value", "value")],
        title="PO Thresholds",
    )


# ---------------------------------------------------------------------------
# users group
# ---------------------------------------------------------------------------

_VALID_ROLES = ["requester", "pcm_approver", "final_approver", "admin"]


@click.group(name="users")
def users_group() -> None:
    """Manage system users."""


@users_group.command("list")
def users_list() -> None:
    """List all users."""
    client = get_client()
    response = client.get("/api/v1/users/")
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No users found.")
        return
    print_table(
        items,
        [
            ("ID", "id"),
            ("Username", "username"),
            ("Email", "email"),
            ("Role", "role"),
            ("Staff", "is_staff"),
        ],
        title="Users",
    )


@users_group.command("set-role")
@click.argument("user_id", type=int)
@click.argument("role", type=click.Choice(_VALID_ROLES))
def users_set_role(user_id: int, role: str) -> None:
    """Set the role for a user (admin only)."""
    client = get_client()
    response = client.patch(f"/api/v1/users/{user_id}/", data={"role": role})
    if not response.is_success:
        raise SystemExit(1)
    print_success(f"User {user_id} role updated to '{role}'.")


# ---------------------------------------------------------------------------
# expense-categories group
# ---------------------------------------------------------------------------


@click.group(name="expense-categories")
def expense_categories_group() -> None:
    """Manage expense categories."""


@expense_categories_group.command("list")
def ec_list() -> None:
    """List all expense categories."""
    client = get_client()
    response = client.get("/api/v1/expense-categories/")
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No expense categories found.")
        return
    print_table(
        items,
        [("ID", "id"), ("Name", "name"), ("Active", "is_active")],
        title="Expense Categories",
    )


@expense_categories_group.command("create")
def ec_create() -> None:
    """Interactively create a new expense category."""
    name = click.prompt("Category name")
    client = get_client()
    response = client.post("/api/v1/expense-categories/", data={"name": name})
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Expense category created: [{result.get('id')}] {result.get('name')}")


# ---------------------------------------------------------------------------
# logs group
# ---------------------------------------------------------------------------


@click.group(name="logs")
def logs_group() -> None:
    """View approval and email logs."""


@logs_group.command("approvals")
@click.option("--content-type", default=None, help="e.g. orders.purchaserequest")
@click.option("--object-id", default=None, type=int, help="Related object ID")
def logs_approvals(content_type: str | None, object_id: int | None) -> None:
    """Show approval log entries."""
    client = get_client()
    params: dict = {}
    if content_type:
        params["content_type"] = content_type
    if object_id:
        params["object_id"] = object_id
    response = client.get("/api/v1/approval-logs/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No approval logs found.")
        return
    print_table(
        items,
        [
            ("ID", "id"),
            ("Action", "action"),
            ("By", "action_by"),
            ("Comment", "comment"),
            ("Created", "created_at"),
        ],
        title="Approval Logs",
    )


@logs_group.command("emails")
@click.option("--limit", default=50, help="Maximum entries to show")
def logs_emails(limit: int) -> None:
    """Show email notification log entries."""
    client = get_client()
    response = client.get("/api/v1/email-logs/", params={"limit": limit})
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No email logs found.")
        return
    print_table(
        items,
        [
            ("ID", "id"),
            ("Recipient", "recipient"),
            ("Subject", "subject"),
            ("Status", "status"),
            ("Sent At", "sent_at"),
        ],
        title="Email Logs",
    )
