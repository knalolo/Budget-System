"""Views for the orders app (PurchaseRequest CRUD and approval actions)."""
from __future__ import annotations

import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from approvals.services import (
    can_user_approve,
    get_approval_history,
    reset_to_draft_after_rejection,
)
from core.services.file_service import save_attachment, validate_file
from core.services.request_number_service import to_internal_number
from core.services.workflow_delete_service import delete_purchase_request_workflow

from .export_service import (
    export_purchase_request_dataset,
    export_purchase_request_sap_reconciliation,
)
from .forms import PurchaseRequestForm
from .models import Project, PurchaseRequest
from .services import (
    approve_purchase_request,
    reject_purchase_request,
    submit_purchase_request,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PENDING_APPROVAL_STATUSES = ("pending_pcm", "pending_final")
PAGE_SIZE = 20
PURCHASE_REQUEST_ATTACHMENT_FILE_TYPES = {
    "quotation": "Quotation",
    "new_order_list": "New Order List",
}
PR_CREATE_TOKEN_TIMEOUT_SECONDS = 60 * 30


def _purchase_request_status_choices() -> list[tuple[str, str]]:
    """Return list-filter labels using unified workflow wording."""
    labels = {
        "draft": "Draft",
        "pending_pcm": "Pending Purchase Type Approver Review",
        "pending_final": "Pending Final Approver Review",
        "approved": "Approved",
        "rejected": "Rejected",
        "po_sent": "Legacy PO Sent",
        "ordered": "Legacy Ordered",
        "completed": "Legacy Completed",
    }
    return [
        (value, labels.get(value, label))
        for value, label in PurchaseRequest._meta.get_field("status").choices
    ]


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------


def _build_purchase_request_queryset(user, params):
    """Return the filtered purchase request queryset for list/export views."""
    tab = params.get("tab", "my_requests")
    status_filter = params.get("status", "")
    project_filter = params.get("project", "")
    search = params.get("q", "").strip()

    if tab == "pending_approval":
        qs = PurchaseRequest.objects.filter(status__in=PENDING_APPROVAL_STATUSES)
    elif _user_can_view_all_purchase_requests(user):
        qs = PurchaseRequest.objects.all()
    else:
        qs = PurchaseRequest.objects.filter(requester=user)

    if status_filter:
        qs = qs.filter(status=status_filter)
    if project_filter:
        qs = qs.filter(project_id=project_filter)
    if search:
        internal_search = to_internal_number(search, "PR")
        qs = qs.filter(
            Q(vendor__icontains=search)
            | Q(description__icontains=search)
            | Q(request_number__icontains=search)
            | Q(request_number__icontains=internal_search)
        )

    return qs


class PurchaseRequestListView(LoginRequiredMixin, ListView):
    """Paginated list of purchase requests with tab and filter support."""

    model = PurchaseRequest
    template_name = "orders/list.html"
    context_object_name = "purchase_requests"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        qs = _build_purchase_request_queryset(self.request.user, self.request.GET)
        return qs.select_related("requester", "project", "expense_category").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = self.request.GET.get("tab", "my_requests")
        context["status_filter"] = self.request.GET.get("status", "")
        context["project_filter"] = self.request.GET.get("project", "")
        context["search"] = self.request.GET.get("q", "")
        context["projects"] = Project.objects.filter(is_active=True)
        context["status_choices"] = _purchase_request_status_choices()
        context["can_create_purchase_request"] = not _is_approval_only_role(self.request.user)
        context["requests_tab_label"] = (
            "All Requests" if _user_can_view_all_purchase_requests(self.request.user) else "My Requests"
        )
        return context


@login_required
def purchase_request_dataset_export(request):
    """Export the current purchase request list filter as the main dataset CSV."""
    queryset = _build_purchase_request_queryset(request.user, request.GET).order_by("-created_at")
    return export_purchase_request_dataset(queryset)


@login_required
def purchase_request_sap_reconciliation_export(request):
    """Export the current purchase request list filter as SAP reconciliation CSV."""
    queryset = _build_purchase_request_queryset(request.user, request.GET).order_by("-created_at")
    return export_purchase_request_sap_reconciliation(queryset)


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------


class PurchaseRequestCreateView(LoginRequiredMixin, CreateView):
    """Form to create a new PurchaseRequest (saved as draft)."""

    model = PurchaseRequest
    form_class = PurchaseRequestForm
    template_name = "orders/form.html"

    def dispatch(self, request, *args, **kwargs):
        if _is_approval_only_role(request.user):
            return HttpResponse(
                "Approval-only accounts cannot create purchase requests.",
                status=403,
            )
        return super().dispatch(request, *args, **kwargs)

    def _dedupe_cache_key(self, token: str) -> str:
        return f"purchase-request-create:{self.request.user.pk}:{token}"

    def _is_duplicate_create_submission(self) -> bool:
        token = self.request.POST.get("create_token", "").strip()
        if not token:
            return False
        return not cache.add(
            self._dedupe_cache_key(token),
            "submitted",
            timeout=PR_CREATE_TOKEN_TIMEOUT_SECONDS,
        )

    def _redirect_after_duplicate_submission(self):
        latest_request = (
            PurchaseRequest.objects.filter(requester=self.request.user)
            .order_by("-created_at")
            .first()
        )
        messages.info(
            self.request,
            "This purchase request was already submitted. Opening the existing request.",
        )
        if latest_request is None:
            return redirect("orders:purchase-request-list")
        return redirect("orders:purchase-request-detail", pk=latest_request.pk)

    def form_valid(self, form):
        if self._is_duplicate_create_submission():
            return self._redirect_after_duplicate_submission()

        uploaded_files = self.request.FILES.getlist("attachment_files")

        try:
            attachment_type = _clean_purchase_request_attachment_type(
                self.request.POST.get("attachment_file_type", "quotation")
            )
            _validate_purchase_request_attachments(uploaded_files)
        except ValidationError as exc:
            form.add_error(None, _validation_error_message(exc))
            return self.form_invalid(form)

        instance = form.save(commit=False)
        instance.requester = self.request.user
        instance.status = "draft"
        instance.save()
        form.save_line_items(instance)

        _save_purchase_request_attachments(
            purchase_request=instance,
            uploaded_files=uploaded_files,
            uploaded_by=self.request.user,
            file_type=attachment_type,
        )

        action = self.request.POST.get("action", "draft")
        if action == "submit":
            try:
                instance = submit_purchase_request(instance)
                messages.success(
                    self.request,
                    f"Purchase request {instance.workflow_number} submitted for approval.",
                )
            except ValidationError as exc:
                messages.warning(
                    self.request,
                    f"Saved as draft. Could not submit: {exc.message}",
                )
        else:
            messages.success(self.request, f"Purchase request {instance.workflow_number} created as draft.")

        return redirect("orders:purchase-request-detail", pk=instance.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "New Purchase Request"
        context["is_create"] = True
        context["create_token"] = secrets.token_urlsafe(24)
        context["attachment_type_options"] = PURCHASE_REQUEST_ATTACHMENT_FILE_TYPES.items()
        context["selected_attachment_type"] = self.request.POST.get(
            "attachment_file_type",
            "quotation",
        )
        return context


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class PurchaseRequestDetailView(LoginRequiredMixin, DetailView):
    """Read-only detail page for a single PurchaseRequest."""

    model = PurchaseRequest
    template_name = "orders/detail.html"
    context_object_name = "purchase_request"

    def get_queryset(self):
        qs = PurchaseRequest.objects.select_related("requester", "project", "expense_category")
        if _user_can_view_all_purchase_requests(self.request.user):
            return qs
        return qs.filter(requester=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pr = self.object
        can_manage_request = _can_manage_purchase_request(self.request.user, pr)
        approval_history = get_approval_history(pr).select_related("action_by")
        can_approve, _ = can_user_approve(pr, self.request.user)
        latest_payment_release = pr.latest_payment_release
        payment_draft = pr.latest_payment_draft
        rejected_payment = (
            latest_payment_release
            if latest_payment_release is not None and latest_payment_release.status == "rejected"
            else None
        )
        has_standard_payment_release = pr.payment_releases.filter(payment_type="standard").exists()
        context["approval_history"] = approval_history
        context["can_approve"] = can_approve
        context["can_manage_request"] = can_manage_request
        context["can_delete_request"] = _can_delete_purchase_request(self.request.user, pr)
        context["attachments"] = pr.attachments.select_related("uploaded_by")
        context["attachment_type_options"] = PURCHASE_REQUEST_ATTACHMENT_FILE_TYPES.items()
        context["selected_attachment_type"] = "quotation"
        context["has_payment_release"] = latest_payment_release is not None
        context["has_standard_payment_release"] = has_standard_payment_release
        context["first_payment_release"] = latest_payment_release
        latest_delivery_submission = pr.latest_delivery_submission
        open_delivery_submission = pr.latest_open_delivery_submission
        context["latest_delivery_submission"] = latest_delivery_submission
        context["open_delivery_submission"] = open_delivery_submission
        context["has_delivery_submission"] = latest_delivery_submission is not None
        context["workflow_stage"] = pr.workflow_stage
        context["workflow_completed"] = pr.workflow_completed
        context["can_submit_goods"] = can_manage_request and pr.can_submit_goods
        context["can_submit_payment"] = can_manage_request and pr.can_submit_payment
        context["payment_draft"] = payment_draft
        context["show_execution_tracking"] = pr.is_execution_ready
        context["delivery_submission_create_url"] = (
            reverse("deliveries:update", args=[open_delivery_submission.pk])
            if open_delivery_submission is not None
            else f"{reverse('deliveries:create')}?purchase_request={pr.pk}"
        )
        payment_type = "standard" if pr.delivered_quantity > 0 else "advance"
        editable_payment = payment_draft or rejected_payment
        context["payment_release_create_url"] = (
            reverse("payments:update", args=[editable_payment.pk])
            if editable_payment is not None
            else f"{reverse('payments:create')}?purchase_request={pr.pk}&payment_type={payment_type}"
        )
        context["advance_payment_create_url"] = (
            f"{reverse('payments:create')}?purchase_request={pr.pk}&payment_type=advance"
        )
        return context


# ---------------------------------------------------------------------------
# Update view
# ---------------------------------------------------------------------------


class PurchaseRequestUpdateView(LoginRequiredMixin, UpdateView):
    """Form to edit a draft or rejected PurchaseRequest."""

    model = PurchaseRequest
    form_class = PurchaseRequestForm
    template_name = "orders/form.html"

    def dispatch(self, request, *args, **kwargs):
        pr = get_object_or_404(PurchaseRequest, pk=kwargs["pk"])
        if not _can_manage_purchase_request(request.user, pr):
            return HttpResponse("You do not have permission to edit this purchase request.", status=403)
        if not pr.can_be_edited:
            messages.error(request, "Only draft or rejected purchase requests can be edited.")
            return redirect("orders:purchase-request-detail", pk=pr.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.save()
        form.save_line_items(instance)
        action = self.request.POST.get("action", "draft")
        if action == "submit":
            try:
                instance = submit_purchase_request(instance)
                messages.success(
                    self.request,
                    f"Purchase request {instance.workflow_number} submitted for approval.",
                )
            except ValidationError as exc:
                messages.warning(
                    self.request,
                    f"Saved. Could not submit: {exc.message}",
                )
        else:
            instance = reset_to_draft_after_rejection(instance, actor=self.request.user)
            messages.success(self.request, f"Purchase request {instance.workflow_number} saved.")
        return redirect("orders:purchase-request-detail", pk=instance.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit {self.object.workflow_number}"
        context["is_create"] = False
        context["purchase_request"] = self.object
        context["attachment_type_options"] = PURCHASE_REQUEST_ATTACHMENT_FILE_TYPES.items()
        context["selected_attachment_type"] = self.request.POST.get(
            "attachment_file_type",
            "quotation",
        )
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
    if not _can_manage_purchase_request(request.user, pr):
        return HttpResponse("Only the requester or admin can submit this purchase request.", status=403)

    try:
        updated_pr = submit_purchase_request(pr)
        messages.success(
            request,
            f"Purchase request {updated_pr.workflow_number} submitted for approval.",
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
            f"Purchase request {updated_pr.workflow_number} approved.",
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
            f"Purchase request {updated_pr.workflow_number} rejected.",
        )
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        return _htmx_detail_redirect(request, pk)
    return redirect("orders:purchase-request-detail", pk=pk)


@login_required
def purchase_request_delete(request, pk):
    """Delete a draft PR or, for admin, the entire linked workflow."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return redirect("orders:purchase-request-detail", pk=pk)
    if not _can_delete_purchase_request(request.user, pr):
        return HttpResponse("You do not have permission to delete this purchase request.", status=403)

    workflow_number = pr.workflow_number
    if _is_admin(request.user):
        delete_purchase_request_workflow(pr)
        messages.success(request, f"{workflow_number} workflow deleted.")
    else:
        pr.delete()
        messages.success(request, f"{workflow_number} draft purchase request deleted.")
    return redirect("orders:purchase-request-list")


@login_required
def purchase_request_upload(request, pk):
    """Handle file upload via HTMX POST and return updated attachments partial."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method != "POST":
        return HttpResponse(status=405)
    if not _can_manage_purchase_request(request.user, pr):
        return HttpResponse("Only the requester or admin can upload purchase request attachments.", status=403)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return HttpResponse("No file provided.", status=400)

    try:
        file_type = _clean_purchase_request_attachment_type(
            request.POST.get("file_type", "quotation")
        )
    except ValidationError as exc:
        return HttpResponse(_validation_error_message(exc), status=400)

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


def _get_role(user) -> str:
    profile = _get_profile(user)
    return profile.primary_role if profile is not None else "requester"


def _get_profile(user):
    try:
        return user.profile
    except AttributeError:
        return None


def _is_approval_only_role(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.is_approval_only)


def _user_can_view_all_purchase_requests(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.can_view_all_requests)


def _can_manage_purchase_request(user, purchase_request: PurchaseRequest) -> bool:
    profile = _get_profile(user)
    return purchase_request.requester == user or bool(profile and profile.is_admin)


def _is_admin(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.is_admin)


def _can_delete_purchase_request(user, purchase_request: PurchaseRequest) -> bool:
    if _is_admin(user):
        return True
    return purchase_request.requester == user and purchase_request.can_be_deleted


def _clean_purchase_request_attachment_type(raw_value: str) -> str:
    """Return a validated attachment file type for purchase request uploads."""
    file_type = (raw_value or "quotation").strip()
    if file_type not in PURCHASE_REQUEST_ATTACHMENT_FILE_TYPES:
        raise ValidationError("Attachment type must be Quotation or New Order List.")
    return file_type


def _validate_purchase_request_attachments(uploaded_files) -> None:
    """Validate all uploaded files before persisting the purchase request."""
    for uploaded_file in uploaded_files:
        validate_file(uploaded_file)


def _save_purchase_request_attachments(
    purchase_request: PurchaseRequest,
    uploaded_files,
    uploaded_by,
    file_type: str,
) -> None:
    """Persist uploaded attachments for a purchase request."""
    for uploaded_file in uploaded_files:
        save_attachment(
            uploaded_file=uploaded_file,
            content_object=purchase_request,
            file_type=file_type,
            uploaded_by=uploaded_by,
        )


def _validation_error_message(exc: ValidationError) -> str:
    """Return a stable single-line message from a Django ValidationError."""
    if hasattr(exc, "messages") and exc.messages:
        return str(exc.messages[0])
    if hasattr(exc, "message"):
        return str(exc.message)
    return str(exc)
