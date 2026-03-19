"""Template-based views for the payments app (PaymentRelease)."""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from core.services.file_service import save_attachment

from .forms import PaymentReleaseForm
from .models import PaymentRelease
from .services import (
    approve_payment_release,
    reject_payment_release,
    submit_payment_release,
)

logger = logging.getLogger(__name__)

_LOGIN_REQUIRED = method_decorator(login_required, name="dispatch")


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseListView(View):
    """Display all PaymentRelease records the user can see."""

    template_name = "payments/list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        qs = PaymentRelease.objects.select_related(
            "requester", "project", "expense_category"
        ).order_by("-created_at")

        # Non-approvers see only their own records
        role = _get_role(request.user)
        if role not in ("pcm_approver", "final_approver", "admin"):
            qs = qs.filter(requester=request.user)

        status_filter = request.GET.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        context = {
            "payment_releases": qs,
            "status_filter": status_filter,
            "status_choices": _status_choices(),
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseCreateView(View):
    """Create a new PaymentRelease."""

    template_name = "payments/form.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = PaymentReleaseForm()
        return render(request, self.template_name, {"form": form, "is_create": True})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = PaymentReleaseForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.requester = request.user
            payment.save()
            messages.success(request, f"Payment release {payment.request_number} created.")
            return redirect("payments:detail", pk=payment.pk)
        return render(request, self.template_name, {"form": form, "is_create": True})


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
        _check_can_view(request.user, payment)
        context = {
            "payment": payment,
            "can_edit": payment.can_be_edited and payment.requester == request.user,
            "can_approve": _can_approve(request.user, payment),
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Update view
# ---------------------------------------------------------------------------

@_LOGIN_REQUIRED
class PaymentReleaseUpdateView(View):
    """Edit a draft PaymentRelease."""

    template_name = "payments/form.html"

    def _get_payment(self, request: HttpRequest, pk: int) -> PaymentRelease:
        payment = get_object_or_404(PaymentRelease, pk=pk)
        if payment.requester != request.user and not _is_admin(request.user):
            raise PermissionError
        if not payment.can_be_edited:
            raise ValidationError("Only draft payment releases can be edited.")
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
        return render(request, self.template_name, {"form": form, "payment": payment, "is_create": False})

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
            form.save()
            messages.success(request, "Payment release updated.")
            return redirect("payments:detail", pk=pk)
        return render(request, self.template_name, {"form": form, "payment": payment, "is_create": False})


# ---------------------------------------------------------------------------
# HTMX action views
# ---------------------------------------------------------------------------

@login_required
def submit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Submit a draft PaymentRelease for approval (POST only)."""
    if request.method != "POST":
        return HttpResponseForbidden()

    payment = get_object_or_404(PaymentRelease, pk=pk)
    if payment.requester != request.user:
        return HttpResponseForbidden("Only the requester can submit this record.")

    try:
        submit_payment_release(payment)
        messages.success(request, f"{payment.request_number} submitted for approval.")
    except ValidationError as exc:
        messages.error(request, str(exc.message))

    if request.headers.get("HX-Request"):
        payment.refresh_from_db()
        return render(request, "payments/_detail_status.html", {"payment": payment})
    return redirect("payments:detail", pk=pk)


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
        messages.success(request, f"{payment.request_number} approved.")
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
        messages.success(request, f"{payment.request_number} rejected.")
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
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        messages.error(request, "No file provided.")
        return redirect("payments:detail", pk=pk)

    file_type = request.POST.get("file_type", "invoice")
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
            {"payment": payment, "attachments": payment.attachments.all()},
        )
    return redirect("payments:detail", pk=pk)


# ---------------------------------------------------------------------------
# HTMX table partial (for list page refresh)
# ---------------------------------------------------------------------------

@login_required
def list_table_partial(request: HttpRequest) -> HttpResponse:
    """Return the payments table partial for HTMX refresh."""
    qs = PaymentRelease.objects.select_related(
        "requester", "project", "expense_category"
    ).order_by("-created_at")

    role = _get_role(request.user)
    if role not in ("pcm_approver", "final_approver", "admin"):
        qs = qs.filter(requester=request.user)

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(
        request,
        "payments/_list_table.html",
        {"payment_releases": qs},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_role(user) -> str:
    try:
        return user.userprofile.role
    except AttributeError:
        return "requester"


def _is_admin(user) -> bool:
    return _get_role(user) == "admin"


def _check_can_view(user, payment: PaymentRelease) -> None:
    """Raise PermissionError if *user* cannot view *payment*."""
    role = _get_role(user)
    if role not in ("pcm_approver", "final_approver", "admin"):
        if payment.requester != user:
            raise PermissionError


def _can_approve(user, payment: PaymentRelease) -> bool:
    """Return True if *user* may approve *payment* at its current stage."""
    role = _get_role(user)
    if payment.status == "pending_pcm":
        return role in ("pcm_approver", "admin") and payment.requester != user
    if payment.status == "pending_final":
        return role in ("final_approver", "admin") and payment.requester != user
    return False


def _status_choices() -> list[tuple[str, str]]:
    """Return all payment status choices including an empty 'All' option."""
    from django.conf import settings
    return [("", "All statuses")] + list(settings.PAYMENT_STATUS_CHOICES)
