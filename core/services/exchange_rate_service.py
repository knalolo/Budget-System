"""Helpers for converting purchase values into SGD using latest FX rates."""

from __future__ import annotations

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.core.cache import cache

logger = logging.getLogger(__name__)

_FX_CACHE_TIMEOUT_SECONDS = 60 * 60 * 6
_FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1/latest"
_TWO_DP = Decimal("0.01")


def get_latest_rate_to_sgd(currency: str) -> Decimal:
    """Return the latest available conversion rate from *currency* to SGD."""
    normalized_currency = (currency or "SGD").upper()
    if normalized_currency == "SGD":
        return Decimal("1.00")

    cache_key = f"fx-rate:{normalized_currency}:SGD"
    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        return Decimal(str(cached_rate))

    query = urlencode({"base": normalized_currency, "symbols": "SGD"})
    request_url = f"{_FRANKFURTER_BASE_URL}?{query}"

    try:
        with urlopen(request_url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as exc:
        logger.warning("Could not fetch FX rate for %s -> SGD: %s", normalized_currency, exc)
        raise RuntimeError(f"Could not fetch FX rate for {normalized_currency} -> SGD.") from exc

    raw_rate = payload.get("rates", {}).get("SGD")
    if raw_rate is None:
        raise RuntimeError(f"No SGD conversion rate returned for {normalized_currency}.")

    rate = Decimal(str(raw_rate))
    cache.set(cache_key, str(rate), _FX_CACHE_TIMEOUT_SECONDS)
    return rate


def convert_amount_to_sgd(amount, currency: str) -> Decimal:
    """Convert *amount* into SGD using the latest available FX rate."""
    normalized_amount = Decimal(str(amount or "0"))
    rate = get_latest_rate_to_sgd(currency)
    return (normalized_amount * rate).quantize(_TWO_DP, rounding=ROUND_HALF_UP)
