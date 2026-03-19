"""Rich output formatting helpers for the procurement CLI."""
from __future__ import annotations

from typing import Any

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Table / Detail output
# ---------------------------------------------------------------------------


def print_table(
    data: list[dict],
    columns: list[str | tuple[str, str]],
    title: str | None = None,
) -> None:
    """Render a list of dicts as a rich Table.

    ``columns`` may contain plain strings (used as both header and key)
    or 2-tuples of (header_label, dict_key).
    """
    table = Table(title=title, show_lines=True)
    col_defs: list[tuple[str, str]] = []
    for col in columns:
        if isinstance(col, tuple):
            label, key = col
        else:
            label = key = col
        table.add_column(label, overflow="fold")
        col_defs.append((label, key))

    for row in data:
        table.add_row(*[str(row.get(key, "")) for _, key in col_defs])

    console.print(table)


def print_detail(data: dict, title: str | None = None) -> None:
    """Render a dict as a key-value Panel."""
    lines = []
    for key, value in data.items():
        lines.append(f"[bold]{key}[/bold]: {value}")
    content = "\n".join(lines)
    console.print(Panel(content, title=title or "Detail", expand=False))


# ---------------------------------------------------------------------------
# Status messages
# ---------------------------------------------------------------------------


def print_success(message: str) -> None:
    """Print a green success message."""
    rprint(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print a red error message."""
    rprint(f"[red]{message}[/red]")


def print_warning(message: str) -> None:
    """Print a yellow warning message."""
    rprint(f"[yellow]{message}[/yellow]")


# ---------------------------------------------------------------------------
# JSON / currency helpers
# ---------------------------------------------------------------------------


def print_json(data: Any) -> None:
    """Pretty-print data as syntax-highlighted JSON."""
    import json

    from rich.syntax import Syntax

    text = json.dumps(data, indent=2, default=str)
    console.print(Syntax(text, "json"))


def format_currency(amount: str | float | None, currency: str) -> str:
    """Return a nicely formatted currency string, e.g. 'SGD 1,234.56'."""
    if amount is None:
        return f"{currency} -"
    try:
        numeric = float(amount)
        return f"{currency} {numeric:,.2f}"
    except (ValueError, TypeError):
        return f"{currency} {amount}"
