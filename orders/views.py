"""Views for the orders app (PurchaseRequest CRUD and approval actions)."""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from approvals.services import can_user_approve, get_approval_history
from core.services.file_service import save_attachment

from .forms import PurchaseRequestForm
from .models import ExpenseCategory, Project, PurchaseRequest
from .services import (
    approve_purchase_request,
    mark_ordered,
    mark_po_sent,
    reject_purchase_request,
    submit_purchase_request,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PENDING_APPROVAL_STATUSES = ("pending_pcm", "pending_final")
PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------


class PurchaseRequestListView(LoginRequiredMixin, ListView):
    """Paginated list of purchase requests with tab and filter support."""

    model = PurchaseRequest
    template_name = "orders/list.html"
    context_object_name = "purchase_requests"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        tab = self.request.GET.get("tab", "my_requests")
        status_filter = self.request.GET.get("status", "")
        project_filter = self.request.GET.get("project", "")
        search = self.request.GET.get("q", "").strip()

        if tab == "pending_approval":
            qs = PurchaseRequest.objects.filter(
                status__in=PENDING_APPROVAL_STATUSES
            )
        else:
            qs = PurchaseRequest.objects.filter(requester=self.request.user)

        if status_filter:
            qs = qs.filter(status=status_filter)
        if project_filter:
            qs = qs.filter(project_id=project_filter)
        if search:
            qs = qs.filter(
                vendor__icontains=search
            ) | qs.filter(
                description__icontains=search
            ) | qs.filter(
                request_number__icontains=search
            )

        return qs.select_related("requester", "project", "expense_category").order_by(
            "-created_at"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = self.request.GET.get("tab", "my_requests")
        context["status_filter"] = self.request.GET.get("status", "")
        context["project_filter"] = self.request.GET.get("project", "")
        context["search"] = self.request.GET.get("q", "")
        context["projects"] = Project.objects.filter(is_active=True)
        context["status_choices"] = PurchaseRequest._meta.get_field("status").choices
        return context


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------


class PurchaseRequestCreateView(LoginRequiredMixin, CreateView):
    """Form to create a new PurchaseRequest (saved as draft)."""

    model = PurchaseRequest
    form_class = PurchaseRequestForm
    template_name = "orders/form.html"

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.requester = self.request.user
        instance.status = "draft"
        instance.save()

        action = self.request.POST.get("action", "draft")
        if action == "submit":
            try:
                instance = submit_purchase_request(instance)
                messages.success(
                    self.request,
                    f"Purchase request {instance.request_number} submitted for approval.",
                )
            except ValidationError as exc:
                messages.warning(
                    self.request,
                    f"Saved as draft. Could not submit: {exc.message}",
                )
        else:
            messages.success(self.request, f"Purchase request {instance.request_number} created as draft.")

        return redirect("orders:purchase-request-detail", pk=instance.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Purchase Request"
        context["is_create"] = True
        return context


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class PurchaseRequestDetailView(LoginRequiredMixin, DetailView):
    """Read-only detail page for a single PurchaseRequest."""

    model = PurchaseRequest
    template_name = "orders/detail.html"
    context_object_name = "purchase_request"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pr = self.object
        approval_history = get_approval_history(pr).select_related("action_by")
        can_approve, _ = can_user_approve(pr, self.request.user)
        context["approval_history"] = approval_history
        context["can_approve"] = can_approve
        context["attachments"] = pr.attachments.select_related("uploaded_by")
        return context


# ---------------------------------------------------------------------------
# Update view
# ---------------------------------------------------------------------------


class PurchaseRequestUpdateView(LoginRequiredMixin, UpdateView):
    """Form to edit a draft PurchaseRequest."""

    model = PurchaseRequest
    form_class = PurchaseRequestForm
    template_name = "orders/form.html"

    def dispatch(self, request, *args, **kwargs):
        pr = get_object_or_404(PurchaseRequest, pk=kwargs["pk"])
        if not pr.can_be_edited:
            messages.error(request, "Only draft purchase requests can be edited.")
            return redirect("orders:purchase-request-detail", pk=pr.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        instance = form.save()
        action = self.request.POST.get("action", "draft")
        if action == "submit":
            try:
                instance = submit_purchase_request(instance)
                messages.success(
                    self.request,
                    f"Purchase request {instance.request_number} submitted for approval.",
                )
            except ValidationError as exc:
                messages.warning(
                    self.request,
                    f"Saved. Could not submit: {exc.message}",
                )
        else:
            messages.success(self.request, f"Purchase request {instance.request_number} saved.")
        return redirect("orders:purchase-request-detail", pk=instance.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit {self.object.request_number}"
        context["is_create"] = False
        context["purchase_request"] = self.object
        return context


# ---------------------------------------------------------------------------
# HTMX action views
# ---------------------------------------------------------------------------


@login_required
def purchase_request_submit(request, pk):
    """Submit a draft purchase request for approval (POST)."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)

    try:
        updated_pr = submit_purchase_request(pr)
        messages.success(
            request,
            f"Purchase request {updated_pr.request_number} submitted for approval.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_approve(request, pk):
    """Approve a pending purchase request (POST)."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)

    comment = request.POST.get("comment", "")

    can_approve, reason = can_user_approve(pr, request.user)
    if not can_approve:
        messages.error(request, reason)
        if request.headers.get("HX-Request"):
            return _htmx_detail_redirect(request, pk)
        return redirect("orders:purchase-request-detail", pk=pk)

    try:
        updated_pr = approve_purchase_request(pr, request.user, comment)
        messages.success(
            request,
            f"Purchase request {updated_pr.request_number} approved.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_reject(request, pk):
    """Reject a pending purchase request (POST)."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)

    comment = request.POST.get("comment", "")

    can_approve, reason = can_user_approve(pr, request.user)
    if not can_approve:
        messages.error(request, reason)
        if request.headers.get("HX-Request"):
            return _htmx_detail_redirect(request, pk)
        return redirect("orders:purchase-request-detail", pk=pk)

    try:
        updated_pr = reject_purchase_request(pr, request.user, comment)
        messages.success(
            request,
            f"Purchase request {updated_pr.request_number} rejected.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_mark_po_sent(request, pk):
    """Transition an approved PR to po_sent (POST)."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)

    try:
        updated_pr = mark_po_sent(pr)
        messages.success(
            request,
            f"Purchase request {updated_pr.request_number} marked as PO sent.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_mark_ordered(request, pk):
    """Transition an approved/po_sent PR to ordered (POST)."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)

    try:
        updated_pr = mark_ordered(pr)
        messages.success(
            request,
            f"Purchase request {updated_pr.request_number} marked as ordered.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_upload(request, pk):
    """Handle file upload via HTMX POST and return updated attachments partial."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return HttpResponse(status=405)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return HttpResponse("No file provided.", status=400)

    file_type = request.POST.get("file_type", "quotation")

    try:
        save_attachment(
            uploaded_file=uploaded_file,
            content_object=pr,
            file_type=file_type,
            uploaded_by=request.user,
        )
    except ValidationError as exc:
        return HttpResponse(str(exc.message), status=400)

    attachments = pr.attachments.select_related("uploaded_by")
    return render(
        request,
        "orders/_attachments_list.html",
        {"attachments": attachments, "purchase_request": pr},
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _htmx_detail_redirect(request, pk: int) -> HttpResponse:
    """Return an HTMX redirect response to the detail page."""
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse_lazy("orders:purchase-request-detail", kwargs={"pk": pk})
    return response
