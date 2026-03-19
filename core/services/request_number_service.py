"""
Request number generation service.

Generates unique, sequential request numbers in the format:
    <PREFIX>-YYYYMMDD-NNNN

Example: PR-20250319-0001

The sequential counter resets per day and is derived by querying the maximum
existing number for the same prefix and date across all relevant models.
"""
from __future__ import annotations

import re
from datetime import date


_SEQUENCE_RE = re.compile(r"-(\d{4})$")

# Registry of (app_label, model_name) tuples that have a request_number field.
# Models register themselves or we query dynamically.
_REQUEST_NUMBER_MODELS = [
    ("orders", "PurchaseRequest"),
    ("payments", "PaymentRelease"),
    ("deliveries", "DeliverySubmission"),
]


def generate_request_number(prefix: str, *, reference_date: date | None = None) -> str:
    """Generate the next sequential request number for *prefix*."""
    today = reference_date or date.today()
    date_str = today.strftime("%Y%m%d")
    prefix_clean = prefix.upper().strip()
    like_pattern = f"{prefix_clean}-{date_str}-"

    next_seq = _next_sequence(like_pattern)
    return f"{prefix_clean}-{date_str}-{next_seq:04d}"


def _next_sequence(like_pattern: str) -> int:
    """Query all models with request_number fields to find the max sequence."""
    from django.apps import apps

    all_numbers: list[str] = []
    for app_label, model_name in _REQUEST_NUMBER_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
            numbers = list(
                model.objects.filter(
                    request_number__startswith=like_pattern
                ).values_list("request_number", flat=True)
            )
            all_numbers.extend(numbers)
        except LookupError:
            continue

    max_seq = _extract_max_sequence(all_numbers)
    return max_seq + 1


def _extract_max_sequence(numbers: list[str]) -> int:
    """Return the highest 4-digit sequence found in *numbers*, or 0."""
    max_seq = 0
    for number in numbers:
        match = _SEQUENCE_RE.search(number)
        if match:
            seq = int(match.group(1))
            if seq > max_seq:
                max_seq = seq
    return max_seq
