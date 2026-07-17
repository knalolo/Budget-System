"""Template-based views for the payments app (PaymentRelease)."""
from __future__ import annotations

import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from approvals.services import reset_to_draft_after_rejection
from core.services.file_service import save_attachment, validate_file
from core.services.workflow_delete_service import delete_payment_workflow

from .forms import PaymentReleaseForm
from .models import PAYMENT_TYPE_ADVANCE, PAYMENT_TYPE_STANDARD, PaymentRelease
from .services import (
    approve_payment_release,
    reject_payment_release,
    submit_payment_release,
)

logger = logging.getLogger(__name__)

_LOGIN_REQUIRED = method_decorator(login_required, name="dispatch")
PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES = {
    "invoice": "Official Invoice",
    "proforma_invoice": "Proforma Invoice",
}
LINKED_PURCHASE_REQUEST_PARAM = "purchase_request"
ACTIVE_PAYMENT_STATUSES = ("pending_pcm", "pending_final", "approved")
PAYMENT_CREATE_TOKEN_TIMEOUT_SECONDS = 60 * 30


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseListView(View):
    """Display all PaymentRelease records the user can see."""

    template_name = "payments/list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        qs = PaymentRelease.objects.select_related(
            "requester", "project", "expense_category", "purchase_request"
        ).order_by("-created_at")

        profile = _get_profile(request.user)
        if not (profile and profile.can_view_all_requests):
            qs = qs.filter(requester=request.user)

        status_filter = request.GET.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        context = {
            "payment_releases": qs,
            "status_filter": status_filter,
            "status_choices": _status_choices(),
            "can_create_payment_release": not _is_approval_only_role(request.user),
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseCreateView(View):
    """Create a new PaymentRelease."""

    template_name = "payments/form.html"

    def _dedupe_cache_key(self, request: HttpRequest, token: str) -> str:
        return f"payment-release-create:{request.user.pk}:{token}"

    def _is_duplicate_create_submission(self, request: HttpRequest) -> bool:
        token = request.POST.get("create_token", "").strip()
        if not token:
            return False
        return not cache.add(
            self._dedupe_cache_key(request, token),
            "submitted",
            timeout=PAYMENT_CREATE_TOKEN_TIMEOUT_SECONDS,
        )

    def _redirect_after_duplicate_submission(self, request: HttpRequest) -> HttpResponse:
        latest_payment = (
            PaymentRelease.objects.filter(requester=request.user)
            .order_by("-created_at")
            .first()
        )
        messages.info(
            request,
            "This payment release was already submitted. Opening the existing payment release.",
        )
        if latest_payment is None:
            return redirect("payments:list")
        return redirect("payments:detail", pk=latest_payment.pk)

    def get(self, request: HttpRequest) -> HttpResponse:
        if _is_approval_only_role(request.user):
            return HttpResponseForbidden(
                "Approval-only accounts cannot create payment releases."
            )
        try:
            source_purchase_request = _get_linkable_purchase_request(request)
        except PermissionError:
            return HttpResponseForbidden(
                "You do not have permission to use this purchase request."
            )
        requested_payment_type = _requested_payment_type(request, source_purchase_request)
        existing_active_payment = _existing_active_payment_release(source_purchase_request)
        if existing_active_payment is not None:
            messages.info(
                request,
                (
                    f"Payment release {existing_active_payment.workflow_number} already "
                    "exists for this request."
                ),
            )
            return redirect("payments:detail", pk=existing_active_payment.pk)

        existing_draft = _existing_payment_draft(source_purchase_request, request.user)
        if existing_draft is not None:
            messages.info(request, "Opening the existing payment draft for this request.")
            return redirect("payments:update", pk=existing_draft.pk)

        form = PaymentReleaseForm(
            initial=_payment_release_initial_from_purchase_request(
                source_purchase_request,
                requested_payment_type=requested_payment_type,
            )
        )
        return _render_payment_create_form(
            request,
            form,
            source_purchase_request=source_purchase_request,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if _is_approval_only_role(request.user):
            return HttpResponseForbidden(
                "Approval-only accounts cannot create payment releases."
            )
        try:
            source_purchase_request = _get_linkable_purchase_request(request)
        except PermissionError:
            return HttpResponseForbidden(
                "You do not have permission to use this purchase request."
            )
        requested_payment_type = _requested_payment_type(request, source_purchase_request)
        existing_active_payment = _existing_active_payment_release(source_purchase_request)
        if existing_active_payment is not None:
            messages.info(
                request,
                (
                    f"Payment release {existing_active_payment.workflow_number} already "
                    "exists for this request."
                ),
            )
            return redirect("payments:detail", pk=existing_active_payment.pk)

        existing_draft = _existing_payment_draft(source_purchase_request, request.user)
        form_data = _payment_release_form_data(
            request,
            source_purchase_request,
            requested_payment_type=requested_payment_type,
        )
        form = PaymentReleaseForm(form_data, instance=existing_draft)
        uploaded_files = request.FILES.getlist("attachment_files")

        try:
            attachment_type = _clean_payment_attachment_type(
                request.POST.get("attachment_file_type", "invoice")
            )
            _validate_payment_attachments(uploaded_files)
        except ValidationError as exc:
            form.add_error(None, _validation_error_message(exc))
            return _render_payment_create_form(
                request,
                form,
                source_purchase_request=source_purchase_request,
            )

        if form.is_valid():
            if self._is_duplicate_create_submission(request):
                return self._redirect_after_duplicate_submission(request)

            payment = form.save(commit=False)
            payment.requester = request.user
            payment.purchase_request = source_purchase_request
            payment.save()

            _save_payment_attachments(
                payment_release=payment,
                uploaded_files=uploaded_files,
                uploaded_by=request.user,
                file_type=attachment_type,
            )

            action = request.POST.get("action", "draft")
            if action == "submit":
                try:
                    submit_payment_release(payment)
                    messages.success(
                        request,
                        f"Payment release {payment.workflow_number} submitted for approval.",
                    )
                except ValidationError as exc:
                    messages.error(request, _validation_error_message(exc))
                    return redirect("payments:detail", pk=payment.pk)
            else:
                messages.success(
                    request,
                    f"Payment release {payment.workflow_number} saved.",
                )
            return redirect("payments:detail", pk=payment.pk)
        return _render_payment_create_form(
            request,
            form,
            source_purchase_request=source_purchase_request,
        )


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseDetailView(View):
    """Display a single PaymentRelease with its approval history."""

    template_name = "payments/detail.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        payment = get_object_or_404(
            PaymentRelease.objects.select_related(
                "requester",
                "project",
                "expense_category",
                "purchase_request",
                "pcm_approver",
                "final_approver",
            ).prefetch_related(
                "attachments__uploaded_by",
                "approval_logs__action_by",
            ),
            pk=pk,
        )
        try:
            _check_can_view(request.user, payment)
        except PermissionError:
            return HttpResponseForbidden("You do not have permission to view this payment release.")
        context = {
            "payment": payment,
            "can_edit": payment.can_be_edited and payment.requester == request.user,
            "can_delete": _can_delete_payment(request.user, payment),
            "can_manage_payment": _can_manage_payment(request.user, payment),
            "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
            "can_approve": _can_approve(request.user, payment),
            "attachment_type_options": PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES.items(),
            "selected_attachment_type": "invoice",
            "linked_purchase_request_summary": _purchase_request_summary(payment.purchase_request),
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Update view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseUpdateView(View):
    """Edit a draft or rejected PaymentRelease."""

    template_name = "payments/form.html"

    def _get_payment(self, request: HttpRequest, pk: int) -> PaymentRelease:
        payment = get_object_or_404(PaymentRelease, pk=pk)
        if not _can_manage_payment(request.user, payment):
            raise PermissionError
        if not payment.can_be_edited:
            raise ValidationError("Only draft or rejected payment releases can be edited.")
        return payment

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        try:
            payment = self._get_payment(request, pk)
        except PermissionError:
            return HttpResponseForbidden("You do not have permission to edit this record.")
        except ValidationError as exc:
            messages.error(request, str(exc.message))
            return redirect("payments:detail", pk=pk)

        form = PaymentReleaseForm(instance=payment)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "payment": payment,
                "is_create": False,
                "attachment_type_options": PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES.items(),
                "selected_attachment_type": "invoice",
                "source_purchase_request": payment.purchase_request,
                "source_purchase_request_summary": _purchase_request_summary(payment.purchase_request),
                "initial_po_mode": _payment_release_po_mode(payment.purchase_request, form),
                "attachments": payment.attachments.all(),
                "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
            },
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        try:
            payment = self._get_payment(request, pk)
        except PermissionError:
            return HttpResponseForbidden("You do not have permission to edit this record.")
        except ValidationError as exc:
            messages.error(request, str(exc.message))
            return redirect("payments:detail", pk=pk)

        form = PaymentReleaseForm(request.POST, instance=payment)
        if form.is_valid():
            payment = form.save()
            action = request.POST.get("action", "draft")
            if action == "submit":
                try:
                    _sync_no_goods_draft_to_advance_payment(payment)
                    payment = submit_payment_release(payment)
                    messages.success(request, f"{payment.workflow_number} submitted for approval.")
                except ValidationError as exc:
                    messages.warning(request, f"Saved. Could not submit: {_validation_error_message(exc)}")
            else:
                payment = reset_to_draft_after_rejection(payment, actor=request.user)
                messages.success(request, "Payment release updated.")
            return redirect("payments:detail", pk=payment.pk)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "payment": payment,
                "is_create": False,
                "attachment_type_options": PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES.items(),
                "selected_attachment_type": "invoice",
                "source_purchase_request": payment.purchase_request,
                "source_purchase_request_summary": _purchase_request_summary(payment.purchase_request),
                "initial_po_mode": _payment_release_po_mode(payment.purchase_request, form),
                "attachments": payment.attachments.all(),
                "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
            },
        )


# ---------------------------------------------------------------------------
# HTMX action views
# ---------------------------------------------------------------------------

@login_required
def submit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Submit a draft PaymentRelease for approval (POST only)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_manage_payment(request.user, payment):
        return HttpResponseForbidden("Only the requester or admin can submit this record.")

    try:
        _sync_no_goods_draft_to_advance_payment(payment)
        submit_payment_release(payment)
        messages.success(request, f"{payment.workflow_number} submitted for approval.")
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(request, "payments/_detail_status.html", {"payment": payment})
    return redirect("payments:detail", pk=pk)


@login_required
def delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a draft payment release (POST only)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_delete_payment(request.user, payment):
        return HttpResponseForbidden("You do not have permission to delete this payment release.")

    workflow_number = payment.workflow_number
    if _is_admin(request.user):
        delete_payment_workflow(payment)
        messages.success(request, f"{workflow_number} workflow deleted.")
    else:
        payment.delete()
        messages.success(request, f"{workflow_number} draft payment release deleted.")
    return redirect("payments:list")


@login_required
def approve_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Record an approval decision (POST only)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_approve(request.user, payment):
        return HttpResponseForbidden("You are not authorised to approve this record.")

    comment = request.POST.get("comment", "")
    try:
        approve_payment_release(payment, request.user, comment)
        messages.success(request, f"{payment.workflow_number} approved.")
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(request, "payments/_detail_status.html", {"payment": payment})
    return redirect("payments:detail", pk=pk)


@login_required
def reject_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Record a rejection decision (POST only)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_approve(request.user, payment):
        return HttpResponseForbidden("You are not authorised to reject this record.")

    comment = request.POST.get("comment", "")
    try:
        reject_payment_release(payment, request.user, comment)
        messages.success(request, f"{payment.workflow_number} rejected.")
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(request, "payments/_detail_status.html", {"payment": payment})
    return redirect("payments:detail", pk=pk)


@login_required
def upload_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Upload a file attachment (POST only, HTMX-friendly)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_manage_payment(request.user, payment):
        return HttpResponseForbidden("Only the requester or admin can upload payment attachments.")
    if not payment.can_be_edited:
        return HttpResponseForbidden("Only draft or rejected payment releases can change attachments.")
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        messages.error(request, "No file provided.")
        return redirect("payments:detail", pk=pk)

    try:
        file_type = _clean_payment_attachment_type(request.POST.get("file_type", "invoice"))
    except ValidationError as exc:
        messages.error(request, _validation_error_message(exc))
        if request.headers.get("HX-Request"):
            payment.refresh_from_db()
            return render(
                request,
                "payments/_attachments_list.html",
                {
                    "payment": payment,
                    "attachments": payment.attachments.all(),
                    "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
                },
            )
        return redirect("payments:detail", pk=pk)

    try:
        save_attachment(
            uploaded_file=uploaded_file,
            content_object=payment,
            file_type=file_type,
            uploaded_by=request.user,
        )
        messages.success(request, f"File '{uploaded_file.name}' uploaded successfully.")
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(
            request,
            "payments/_attachments_list.html",
            {
                "payment": payment,
                "attachments": payment.attachments.all(),
                "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
            },
        )
    return redirect("payments:detail", pk=pk)


@login_required
def delete_attachment_view(request: HttpRequest, pk: int, attachment_pk: int) -> HttpResponse:
    """Delete one payment attachment when the payment is still editable."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if not _can_manage_payment(request.user, payment):
        return HttpResponseForbidden("Only the requester or admin can delete payment attachments.")
    if not payment.can_be_edited:
        return HttpResponseForbidden("Only draft or rejected payment releases can change attachments.")

    attachment = get_object_or_404(payment.attachments, pk=attachment_pk)
    filename = attachment.original_filename
    if attachment.file:
        attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, f"File '{filename}' deleted.")

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(
            request,
            "payments/_attachments_list.html",
            {
                "payment": payment,
                "attachments": payment.attachments.all(),
                "can_manage_attachments": _can_manage_payment_attachments(request.user, payment),
            },
        )
    return redirect("payments:detail", pk=pk)


# ---------------------------------------------------------------------------
# HTMX table partial (for list page refresh)
# ---------------------------------------------------------------------------

@login_required
def list_table_partial(request: HttpRequest) -> HttpResponse:
    """Return the payments table partial for HTMX refresh."""
    qs = PaymentRelease.objects.select_related(
        "requester", "project", "expense_category", "purchase_request"
    ).order_by("-created_at")

    profile = _get_profile(request.user)
    if not (profile and profile.can_view_all_requests):
        qs = qs.filter(requester=request.user)

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(
        request,
        "payments/_list_table.html",
        {
            "payment_releases": qs,
            "can_create_payment_release": not _is_approval_only_role(request.user),
        },
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_role(user) -> str:
    profile = _get_profile(user)
    return profile.primary_role if profile is not None else "requester"


def _get_profile(user):
    try:
        return user.profile
    except AttributeError:
        return None


def _is_admin(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.is_admin)


def _is_approval_only_role(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.is_approval_only)


def _check_can_view(user, payment: PaymentRelease) -> None:
    """Raise PermissionError if *user* cannot view *payment*."""
    profile = _get_profile(user)
    can_view_all = bool(profile and profile.can_view_all_requests)
    if not can_view_all:
        if payment.requester != user:
            raise PermissionError


def _can_approve(user, payment: PaymentRelease) -> bool:
    """Return True if *user* may approve *payment* at its current stage."""
    profile = _get_profile(user)
    if profile is None:
        return False
    if payment.status == "pending_pcm":
        return profile.can_approve_purchase_type(payment.purchase_type)
    if payment.status == "pending_final":
        return profile.is_final_approver
    return False


def _can_manage_payment(user, payment: PaymentRelease) -> bool:
    return payment.requester == user or _is_admin(user)


def _can_manage_payment_attachments(user, payment: PaymentRelease) -> bool:
    return payment.can_be_edited and _can_manage_payment(user, payment)


def _can_delete_payment(user, payment: PaymentRelease) -> bool:
    if _is_admin(user):
        return True
    return payment.requester == user and payment.can_be_deleted


def _status_choices() -> list[tuple[str, str]]:
    """Return all payment status choices including an empty 'All' option."""
    return [
        ("", "All statuses"),
        ("draft", "Draft"),
        ("pending_pcm", "Pending Purchase Type Approver Review"),
        ("pending_final", "Pending Final Approver Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]


def _render_payment_create_form(
    request: HttpRequest,
    form: PaymentReleaseForm,
    *,
    source_purchase_request=None,
) -> HttpResponse:
    """Render the create form, preserving linked purchase-request context."""
    create_token = request.POST.get("create_token") or secrets.token_urlsafe(24)
    return render(
        request,
        PaymentReleaseCreateView.template_name,
        {
            "form": form,
            "is_create": True,
            "create_token": create_token,
            "attachment_type_options": PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES.items(),
            "selected_attachment_type": request.POST.get(
                "attachment_file_type",
                "invoice",
            ),
            "source_purchase_request": source_purchase_request,
            "source_purchase_request_summary": _purchase_request_summary(source_purchase_request),
            "initial_po_mode": _payment_release_po_mode(source_purchase_request, form),
        },
    )


def _get_linkable_purchase_request(request: HttpRequest):
    """
    Return the purchase request referenced by the request, if any.

    Requesters may only link their own purchase requests. Admins may link any
    purchase request. Missing ids simply return None.
    """
    raw_purchase_request_id = (
        request.POST.get(LINKED_PURCHASE_REQUEST_PARAM)
        or request.GET.get(LINKED_PURCHASE_REQUEST_PARAM)
    )
    if not raw_purchase_request_id:
        return None

    from orders.models import PurchaseRequest

    purchase_request = get_object_or_404(
        PurchaseRequest.objects.select_related("requester", "project", "expense_category"),
        pk=raw_purchase_request_id,
    )

    if purchase_request.requester != request.user and not _is_admin(request.user):
        raise PermissionError

    return purchase_request


def _existing_active_payment_release(purchase_request):
    """Return the active payment that should own this PR payment step."""
    if purchase_request is None:
        return None
    return (
        purchase_request.payment_releases.filter(status__in=ACTIVE_PAYMENT_STATUSES)
        .annotate(
            workflow_priority=models.Case(
                models.When(status="approved", then=models.Value(30)),
                models.When(status="pending_final", then=models.Value(20)),
                models.When(status="pending_pcm", then=models.Value(10)),
                default=models.Value(0),
                output_field=models.IntegerField(),
            )
        )
        .order_by("-workflow_priority", "-updated_at", "-created_at")
        .first()
    )


def _existing_payment_draft(purchase_request, user):
    """Reuse one draft per linked PR so repeated submits do not create duplicates."""
    if purchase_request is None:
        return None
    return (
        purchase_request.payment_releases.filter(status="draft", requester=user)
        .order_by("-updated_at", "-created_at")
        .first()
    )


def _payment_release_initial_from_purchase_request(
    purchase_request,
    *,
    requested_payment_type: str = "standard",
) -> dict:
    """Build initial payment-release form values from a purchase request."""
    if purchase_request is None:
        return {"payment_type": requested_payment_type}

    if requested_payment_type == "advance":
        payment_quantity = purchase_request.ordered_quantity
        total_price = purchase_request.total_price
    else:
        payment_quantity = max(purchase_request.available_standard_payment_quantity, 1)
        total_price = (
            min(
                purchase_request.max_standard_payment_total,
                purchase_request.remaining_payable_total,
            )
            if purchase_request.available_standard_payment_quantity > 0
            else purchase_request.remaining_payable_total
        )

    return {
        "expense_category": purchase_request.expense_category_id,
        "project": purchase_request.project_id,
        "description": purchase_request.description,
        "vendor": purchase_request.vendor,
        "currency": purchase_request.currency,
        "payment_type": requested_payment_type,
        "payment_quantity": payment_quantity,
        "total_price": total_price,
        "justification": purchase_request.justification,
        "po_number": "" if purchase_request.po_required else "N/A",
        "target_payment": purchase_request.target_payment,
    }


def _payment_release_form_data(
    request: HttpRequest,
    purchase_request,
    *,
    requested_payment_type: str,
):
    """Return POST data with server-owned linked-PR fields re-synced.

    The linked purchase request is the source of truth for amount, quantity,
    vendor, project, and payment type. This prevents stale pages or hidden
    fields from creating an invalid Standard Payment before goods are received.
    """
    form_data = request.POST.copy()
    if purchase_request is None:
        return form_data

    initial = _payment_release_initial_from_purchase_request(
        purchase_request,
        requested_payment_type=requested_payment_type,
    )
    for field_name in (
        "expense_category",
        "project",
        "description",
        "vendor",
        "currency",
        "payment_type",
        "payment_quantity",
        "total_price",
        "justification",
    ):
        value = initial.get(field_name)
        form_data[field_name] = "" if value is None else str(value)
    return form_data


def _sync_no_goods_draft_to_advance_payment(payment: PaymentRelease) -> None:
    """Convert stale no-goods Standard Payment drafts to Advance Payment.

    Older pages could create a Standard Payment draft before goods receive was
    recorded. Such drafts cannot be submitted under the current delivery-first
    rule, so submitting them should follow the explicit prepayment path.
    """
    purchase_request = payment.purchase_request
    if (
        purchase_request is None
        or payment.status != "draft"
        or payment.payment_type != PAYMENT_TYPE_STANDARD
        or purchase_request.delivered_quantity > 0
    ):
        return

    payment.payment_type = PAYMENT_TYPE_ADVANCE
    payment.payment_quantity = purchase_request.ordered_quantity
    payment.total_price = purchase_request.total_price
    payment.save(update_fields=["payment_type", "payment_quantity", "total_price", "updated_at"])


def _purchase_request_summary(purchase_request) -> dict | None:
    """Return unified workflow guidance for a linked purchase request."""
    if purchase_request is None:
        return None

    return {
        "ordered_quantity": purchase_request.ordered_quantity,
        "delivered_quantity": purchase_request.delivered_quantity,
        "delivered_total_value": purchase_request.delivered_total_value,
        "remaining_quantity": purchase_request.remaining_quantity,
        "goods_stage": purchase_request.goods_stage,
        "goods_stage_display": purchase_request.goods_stage_display,
        "payment_stage": purchase_request.payment_stage,
        "payment_stage_display": purchase_request.payment_stage_display,
        "workflow_stage": purchase_request.workflow_stage,
        "workflow_stage_display": purchase_request.workflow_stage_display,
        "workflow_completed": purchase_request.workflow_completed,
        "available_standard_payment_quantity": purchase_request.available_standard_payment_quantity,
        "available_standard_payment_total": purchase_request.available_standard_payment_total,
        "max_standard_payment_total": purchase_request.max_standard_payment_total,
        "remaining_payable_total": purchase_request.remaining_payable_total,
    }


def _requested_payment_type(request: HttpRequest, purchase_request) -> str:
    requested_payment_type = (
        request.POST.get("payment_type")
        or request.GET.get("payment_type")
        or "standard"
    )
    if purchase_request is None:
        return requested_payment_type if requested_payment_type in ("standard", "advance") else "standard"
    if requested_payment_type == "advance":
        return "advance"
    if requested_payment_type == "standard" and purchase_request.delivered_quantity > 0:
        return "standard"
    return "advance"


def _payment_release_po_mode(purchase_request, form: PaymentReleaseForm) -> str:
    """Return the initial PO mode for the payment-release form."""
    po_number_value = form["po_number"].value()
    if purchase_request is not None and purchase_request.po_required and not po_number_value:
        return "other"
    if po_number_value and po_number_value != "N/A":
        return "other"
    return "na"


def _clean_payment_attachment_type(raw_value: str) -> str:
    """Return a validated attachment file type for payment releases."""
    file_type = (raw_value or "invoice").strip()
    if file_type not in PAYMENT_RELEASE_ATTACHMENT_FILE_TYPES:
        raise ValidationError(
            "Attachment type must be Official Invoice or Proforma Invoice."
        )
    return file_type


def _validate_payment_attachments(uploaded_files) -> None:
    """Validate all uploaded payment attachments before persisting them."""
    for uploaded_file in uploaded_files:
        validate_file(uploaded_file)


def _save_payment_attachments(
    payment_release: PaymentRelease,
    uploaded_files,
    uploaded_by,
    file_type: str,
) -> None:
    """Persist uploaded attachments for a payment release."""
    for uploaded_file in uploaded_files:
        save_attachment(
            uploaded_file=uploaded_file,
            content_object=payment_release,
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
