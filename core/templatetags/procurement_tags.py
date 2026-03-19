"""
Custom Django template tags and filters for the procurement system.

Load in templates with:
    {% load procurement_tags %}
"""
from __future__ import annotations

from django import template

register = template.Library()


# ---------------------------------------------------------------------------
# status_color
# ---------------------------------------------------------------------------

_STATUS_COLOR_MAP: dict[str, str] = {
    # Purchase Request / Payment statuses
    "draft": "gray",
    "pending_pcm": "yellow",
    "pending_final": "orange",
    "approved": "green",
    "rejected": "red",
    "po_sent": "blue",
    "ordered": "indigo",
    "completed": "teal",
    # Delivery statuses
    "submitted": "blue",
    "saved": "gray",
    # Email log statuses
    "pending": "yellow",
    "sent": "green",
    "failed": "red",
    # Approval decision statuses
    "pending": "yellow",
}


@register.filter(name="status_color")
def status_color(status: str) -> str:
    """
    Return a Tailwind CSS colour name for the given status string.

    Usage::

        <span class="text-{{ order.status|status_color }}-600">
            {{ order.get_status_display }}
        </span>

    Returns ``'gray'`` for unknown statuses.
    """
    return _STATUS_COLOR_MAP.get(str(status).lower(), "gray")


# ---------------------------------------------------------------------------
# currency_symbol
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOL_MAP: dict[str, str] = {
    "SGD": "SG$",
    "USD": "US$",
    "EUR": "EUR",
}


@register.filter(name="currency_symbol")
def currency_symbol(currency_code: str) -> str:
    """
    Return the display symbol for a currency code.

    Usage::

        {{ amount }} {{ order.currency|currency_symbol }}

    Returns the code itself if not recognised.
    """
    return _CURRENCY_SYMBOL_MAP.get(str(currency_code).upper(), str(currency_code))


# ---------------------------------------------------------------------------
# file_size_display
# ---------------------------------------------------------------------------

_SIZE_UNITS = [
    (1_073_741_824, "GB"),
    (1_048_576, "MB"),
    (1_024, "KB"),
]


@register.filter(name="file_size_display")
def file_size_display(size_bytes) -> str:
    """
    Return a human-readable file size string.

    Usage::

        {{ attachment.file_size|file_size_display }}
        {# e.g. "1.4 MB" or "512 KB" #}

    Args:
        size_bytes: Integer number of bytes (or a value coercible to int).

    Returns:
        Formatted string such as ``'2.3 MB'``, ``'512 KB'``, or ``'800 B'``.
    """
    try:
        size = int(size_bytes)
    except (TypeError, ValueError):
        return "0 B"

    for threshold, unit in _SIZE_UNITS:
        if size >= threshold:
            value = size / threshold
            return f"{value:.1f} {unit}"

    return f"{size} B"
