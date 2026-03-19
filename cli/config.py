"""CLI configuration management.

Config file: ~/.procurement-cli.json
Keys stored: api_url, token
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path.home() / ".procurement-cli.json"
_DEFAULT_API_URL = "http://localhost:8000"


def load_config() -> dict:
    """Load config from ~/.procurement-cli.json, returning an empty dict if missing."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    """Persist config dict to ~/.procurement-cli.json."""
    _CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_api_url() -> str:
    """Return the configured API base URL, defaulting to localhost:8000."""
    return load_config().get("api_url") or _DEFAULT_API_URL


def get_token() -> str | None:
    """Return the stored auth token, or None if not configured."""
    return load_config().get("token") or None
