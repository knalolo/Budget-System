"""HTTP client wrapper using httpx for the procurement system API."""
from __future__ import annotations

from typing import Any

import httpx

from cli.config import get_api_url, get_token
from cli.formatters import print_error

_TIMEOUT = 30.0


class ProcurementClient:
    """Thin synchronous httpx wrapper with token auth and error display."""

    def __init__(self, base_url: str, token: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Token {self._token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _handle_error(self, response: httpx.Response) -> None:
        """Print a user-friendly error for non-2xx responses."""
        if response.is_success:
            return
        try:
            data = response.json()
            # Try common DRF error shapes.
            if isinstance(data, dict):
                detail = (
                    data.get("detail")
                    or data.get("non_field_errors")
                    or str(data)
                )
            else:
                detail = str(data)
        except Exception:
            detail = response.text or response.reason_phrase
        print_error(f"HTTP {response.status_code}: {detail}")

    # ------------------------------------------------------------------
    # Public HTTP verbs
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        response = httpx.get(
            self._url(path),
            params=params,
            headers=self._headers(),
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        self._handle_error(response)
        return response

    def post(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        files: dict | None = None,
    ) -> httpx.Response:
        headers = self._headers()
        if files:
            # Let httpx set the multipart Content-Type boundary automatically.
            response = httpx.post(
                self._url(path),
                data=data or {},
                files=files,
                headers=headers,
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
        else:
            headers["Content-Type"] = "application/json"
            response = httpx.post(
                self._url(path),
                json=data or {},
                headers=headers,
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
        self._handle_error(response)
        return response

    def patch(self, path: str, data: dict[str, Any] | None = None) -> httpx.Response:
        headers = {**self._headers(), "Content-Type": "application/json"}
        response = httpx.patch(
            self._url(path),
            json=data or {},
            headers=headers,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        self._handle_error(response)
        return response

    def delete(self, path: str) -> httpx.Response:
        response = httpx.delete(
            self._url(path),
            headers=self._headers(),
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        self._handle_error(response)
        return response


def get_client() -> ProcurementClient:
    """Build a ProcurementClient from the current CLI config."""
    return ProcurementClient(base_url=get_api_url(), token=get_token())
