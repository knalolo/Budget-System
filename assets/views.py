"""Django views for the assets app."""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, ListView

from .forms import AssetRegistrationForm
from .models import AssetItem, AssetRegistration
from .services import export_csv, mark_imported

logger = logging.getLogger(__name__)

PAGE_SIZE = 20

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class AssetRegistrationListView(LoginRequiredMixin, ListView):
    """Paginated list of asset registrations."""

    model = AssetRegistration
    template_name = "assets/list.html"
    context_object_name = "registrations"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        return (
            AssetRegistration.objects.select_related(
                "requester",
                "payment_release",
                "payment_release__purchase_request",
                "purchase_request",
            )
            .prefetch_related("items")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = AssetRegistration._meta.get_field("status").choices
        return ctx


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _parse_items_from_post(post_data) -> list[dict]:
    """Extract inline asset item data from POST (Alpine.js serialised JSON field)."""
    raw = post_data.get("items_json", "[]")
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("Could not parse items_json: %r", raw)
        return []
    if not isinstance(items, list):
        return []
    return items


def _coerce_item(raw: dict) -> dict:
    """Sanitise a single item dict from the JSON payload."""
    purchase_cost = None
    raw_cost = str(raw.get("purchase_cost", "")).strip()
    if raw_cost:
        try:
            purchase_cost = Decimal(raw_cost)
        except InvalidOperation:
            purchase_cost = None

    purchase_date = str(raw.get("purchase_date", "")).strip() or None

    return {
        "asset_name": str(raw.get("asset_name", "")).strip(),
        "asset_tag": str(raw.get("asset_tag", "")).strip(),
        "category": str(raw.get("category", "")).strip(),
        "serial_number": str(raw.get("serial_number", "")).strip(),
        "purchase_date": purchase_date,
        "purchase_cost": purchase_cost,
        "supplier": str(raw.get("supplier", "")).strip(),
        "location": str(raw.get("location", "")).strip(),
        "department": str(raw.get("department", "")).strip(),
        "assigned_to": str(raw.get("assigned_to", "")).strip(),
        "notes": str(raw.get("notes", "")).strip(),
    }


class AssetRegistrationCreateView(LoginRequiredMixin, CreateView):
    """Create a new asset registration with inline item rows."""

    model = AssetRegistration
    form_class = AssetRegistrationForm
    template_name = "assets/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Asset Registration"
        ctx["is_create"] = True
        return ctx

    def form_valid(self, form):
        registration = form.save(commit=False)
        registration.requester = self.request.user
        registration.purchase_request = (
            registration.payment_release.purchase_request
            if registration.payment_release_id
            else None
        )
        registration.save()

        items_data = _parse_items_from_post(self.request.POST)
        valid_items = [
            _coerce_item(item)
            for item in items_data
            if str(item.get("asset_name", "")).strip()
        ]
        for item_data in valid_items:
            AssetItem.objects.create(registration=registration, **item_data)

        messages.success(
            self.request,
            f"Asset registration #{registration.pk} created with {len(valid_items)} item(s).",
        )
        return redirect("assets:detail", pk=registration.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


class AssetRegistrationDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single asset registration."""

    model = AssetRegistration
    template_name = "assets/detail.html"
    context_object_name = "registration"

    def get_queryset(self):
        return AssetRegistration.objects.select_related(
            "requester",
            "payment_release",
            "payment_release__purchase_request",
            "purchase_request",
        ).prefetch_related("items")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["items"] = self.object.items.all()
        return ctx

    def post(self, request, pk):
        """Handle POST actions: export_csv or mark_imported."""
        registration = get_object_or_404(AssetRegistration, pk=pk)
        action = request.POST.get("action")

        if action == "export_csv":
            return export_csv(registration)

        if action == "mark_imported":
            if registration.status != "exported":
                messages.error(
                    request,
                    "Only exported registrations can be marked as imported.",
                )
            else:
                mark_imported(registration)
                messages.success(
                    request,
                    f"Registration #{registration.pk} marked as imported.",
                )
            return redirect("assets:detail", pk=registration.pk)

        messages.error(request, "Unknown action.")
        return redirect("assets:detail", pk=registration.pk)
