"""Procurement CLI entry point.

Install the package and run:
    procurement-cli --help
"""
from __future__ import annotations

import click

from cli.commands.admin_cmds import (
    config_group,
    expense_categories_group,
    logs_group,
    users_group,
)
from cli.commands.assets import assets_group
from cli.commands.auth import auth_group
from cli.commands.debug import debug_group
from cli.commands.delivery_submissions import delivery_submissions_group
from cli.commands.payment_releases import payment_releases_group
from cli.commands.projects import projects_group
from cli.commands.purchase_requests import purchase_requests_group


@click.group()
@click.version_option(package_name="procurement-system", prog_name="procurement-cli")
def cli() -> None:
    """Procurement System CLI.

    Interact with the procurement approval system from the terminal.

    Quick start:
      procurement-cli auth login
      procurement-cli purchase-requests list
    """


# Register all command groups.
cli.add_command(auth_group)
cli.add_command(purchase_requests_group)
cli.add_command(payment_releases_group)
cli.add_command(delivery_submissions_group)
cli.add_command(assets_group)
cli.add_command(projects_group)
cli.add_command(expense_categories_group)
cli.add_command(config_group)
cli.add_command(users_group)
cli.add_command(logs_group)
cli.add_command(debug_group)
