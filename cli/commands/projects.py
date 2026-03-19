"""Project commands."""
from __future__ import annotations

import click

from cli.client import get_client
from cli.formatters import print_detail, print_success, print_table

_PROJECT_COLUMNS = [
    ("ID", "id"),
    ("MC Number", "mc_number"),
    ("Name", "name"),
    ("Active", "is_active"),
    ("Created", "created_at"),
]


@click.group(name="projects")
def projects_group() -> None:
    """Manage projects."""


@projects_group.command("list")
@click.option("--inactive", is_flag=True, default=False, help="Include inactive projects")
def project_list(inactive: bool) -> None:
    """List all projects."""
    client = get_client()
    params: dict = {}
    if not inactive:
        params["is_active"] = "true"
    response = client.get("/api/v1/projects/", params=params)
    if not response.is_success:
        raise SystemExit(1)
    data = response.json()
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        click.echo("No projects found.")
        return
    print_table(items, _PROJECT_COLUMNS, title="Projects")


@projects_group.command("create")
def project_create() -> None:
    """Interactively create a new project."""
    mc_number = click.prompt("MC Number (e.g. MC-2025-001)")
    name = click.prompt("Project name")

    client = get_client()
    response = client.post("/api/v1/projects/", data={"mc_number": mc_number, "name": name})
    if not response.is_success:
        raise SystemExit(1)
    result = response.json()
    print_success(f"Project created: [{result.get('id')}] {result.get('mc_number')} - {result.get('name')}")
    print_detail(
        {
            "ID": result.get("id", ""),
            "MC Number": result.get("mc_number", ""),
            "Name": result.get("name", ""),
            "Active": result.get("is_active", ""),
        },
        title="Project Detail",
    )
