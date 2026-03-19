"""Debug and diagnostic commands."""
from __future__ import annotations

import click

from cli.client import get_client
from cli.config import get_api_url, get_token
from cli.formatters import print_detail, print_error, print_json, print_success, print_warning


@click.group(name="debug")
def debug_group() -> None:
    """Diagnostic and debug commands."""


@debug_group.command("check-health")
def check_health() -> None:
    """Check API server reachability."""
    client = get_client()
    try:
        response = client.get("/")
    except Exception as exc:
        print_error(f"Cannot reach server: {exc}")
        raise SystemExit(1)
    if response.status_code < 500:
        print_success(f"Server reachable. HTTP {response.status_code}")
    else:
        print_error(f"Server returned HTTP {response.status_code}")
        raise SystemExit(1)


@debug_group.command("test-db")
def test_db() -> None:
    """Verify database connectivity via dashboard summary."""
    client = get_client()
    response = client.get("/api/v1/dashboard/summary/")
    if not response.is_success:
        print_error("Database check failed.")
        raise SystemExit(1)
    data = response.json()
    print_success("Database connection OK.")
    print_detail(
        {
            "Total purchase requests": data.get("total_purchase_requests", ""),
            "Total payment releases": data.get("total_payment_releases", ""),
            "Total delivery submissions": data.get("total_delivery_submissions", ""),
        },
        title="Dashboard Summary",
    )


@debug_group.command("test-email")
@click.argument("to_address")
def test_email(to_address: str) -> None:
    """Display email configuration (sending test emails requires server support)."""
    api_url = get_api_url()
    token = get_token()
    print_warning("Note: A dedicated test-email API endpoint is not exposed.")
    print_detail(
        {
            "API URL": api_url,
            "Authenticated": "Yes" if token else "No",
            "Would send to": to_address,
        },
        title="Email Test (Config Display)",
    )
    click.echo(
        "To test email delivery, use the Django management command:\n"
        "  python manage.py shell -c \"from django.core.mail import send_mail; "
        f"send_mail('Test', 'Hello', None, ['{to_address}'])\""
    )


@debug_group.command("seed")
def seed() -> None:
    """Seed the database with sample data (requires server-side management command)."""
    print_warning(
        "Seeding is performed via the Django management command:\n"
        "  python manage.py seed_data\n\n"
        "This CLI command is a reminder only."
    )


@debug_group.command("reset")
@click.option("--confirm", is_flag=True, default=False, help="Skip confirmation prompt")
def reset(confirm: bool) -> None:
    """WARNING: Drop all procurement data (irreversible)."""
    print_warning("This will DELETE all purchase requests, payment releases, delivery submissions, and attachments.")
    if not confirm:
        if not click.confirm("Are you absolutely sure? This cannot be undone.", default=False):
            click.echo("Reset cancelled.")
            return
    print_warning(
        "Full data reset is a Django management operation.\n"
        "Run:  python manage.py flush --no-input\n"
        "or drop and recreate your database."
    )
