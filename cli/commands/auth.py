"""Auth commands: login and whoami."""
from __future__ import annotations

import click

from cli.client import ProcurementClient
from cli.config import get_api_url, get_token, load_config, save_config
from cli.formatters import print_detail, print_error, print_success


@click.group(name="auth")
def auth_group() -> None:
    """Authentication commands."""


@auth_group.command("login")
def login() -> None:
    """Prompt for API URL and Token, then save to config."""
    current_url = get_api_url()
    api_url = click.prompt("API URL", default=current_url)
    token = click.prompt("Auth Token", hide_input=True)

    if not token.strip():
        print_error("Token cannot be empty.")
        raise SystemExit(1)

    config = load_config()
    new_config = {**config, "api_url": api_url.rstrip("/"), "token": token.strip()}
    save_config(new_config)

    # Verify credentials immediately.
    client = ProcurementClient(base_url=api_url, token=token.strip())
    response = client.get("/api/v1/auth/me/")
    if response.is_success:
        data = response.json()
        print_success(f"Logged in as {data.get('username', '?')} ({data.get('email', '')})")
    else:
        print_error("Credentials saved but verification failed. Check your token.")


@auth_group.command("whoami")
def whoami() -> None:
    """Display the currently authenticated user's profile."""
    token = get_token()
    if not token:
        print_error("Not logged in. Run: procurement-cli auth login")
        raise SystemExit(1)

    from cli.client import get_client

    client = get_client()
    response = client.get("/api/v1/auth/me/")
    if not response.is_success:
        raise SystemExit(1)

    data = response.json()
    print_detail(
        {
            "Username": data.get("username", ""),
            "Email": data.get("email", ""),
            "Full name": f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            "Role": data.get("role", ""),
            "Is staff": data.get("is_staff", ""),
        },
        title="Current User",
    )
