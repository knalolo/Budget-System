"""Template views for the deliveries app."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView

from .forms import DeliverySubmissionForm
from .models import DeliverySubmission
from .services import create_delivery_submission

logger = logging.getLogger(__name__)


class DeliverySubmissionListView(LoginRequiredMixin, ListView):
    """List all delivery submissions."""

    model = DeliverySubmission
    template_name = "deliveries/list.html"
    context_object_name = "submissions"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            DeliverySubmission.objects.select_related("requester")
            .prefetch_related("attachments")
            .all()
        )
        vendor = self.request.GET.get("vendor", "").strip()
        status_filter = self.request.GET.get("status", "").strip()
        if vendor:
            qs = qs.filter(vendor__icontains=vendor)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["vendor_filter"] = self.request.GET.get("vendor", "")
        ctx["status_filter"] = self.request.GET.get("status", "")
        return ctx


class DeliverySubmissionCreateView(LoginRequiredMixin, object):
    """Create a delivery submission (submit immediately)."""

    pass


@login_required
def delivery_submission_create(request):
    """Handle GET (render form) and POST (create submission) for delivery submissions."""
    try:
        source_purchase_request = _get_linkable_purchase_request(request)
    except PermissionError:
        return HttpResponseForbidden("You do not have permission to use this purchase request.")

    if request.method == "POST":
        form = DeliverySubmissionForm(request.POST)
        files = request.FILES.getlist("files")

        if not files:
            form.add_error(None, "At least one DO/SO document must be attached.")

        if form.is_valid() and files:
            try:
                submission = create_delivery_submission(
                    data={
                        **form.cleaned_data,
                        "purchase_request": source_purchase_request,
                    },
                    user=request.user,
                    files=files,
                )
                messages.success(
                    request,
                    f"Delivery submission {submission.request_number} created successfully.",
                )
                return redirect("deliveries:detail", pk=submission.pk)
            except Exception:
                logger.exception("Failed to create delivery submission.")
                messages.error(
                    request,
                    "An unexpected error occurred. Please try again.",
                )
    else:
        form = DeliverySubmissionForm(
            initial=_delivery_initial_from_purchase_request(source_purchase_request)
        )

    return render(
        request,
        "deliveries/form.html",
        {
            "form": form,
            "source_purchase_request": source_purchase_request,
        },
    )


class DeliverySubmissionDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single delivery submission."""

    model = DeliverySubmission
    template_name = "deliveries/detail.html"
    context_object_name = "submission"

    def get_queryset(self):
        return DeliverySubmission.objects.select_related(
            "requester", "purchase_request"
        ).prefetch_related("attachments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submission = self.object
        linked_purchase_request = submission.purchase_request
        context["linked_purchase_request"] = linked_purchase_request
        context["can_create_payment_release"] = bool(
            linked_purchase_request and linked_purchase_request.is_ready_for_payment
        )
        if linked_purchase_request is not None:
            context["payment_release_create_url"] = (
                f"{reverse('payments:create')}?purchase_request={linked_purchase_request.pk}"
            )
        return context


@login_required
def delivery_submission_upload(request, pk: int):
    """
    HTMX endpoint: upload additional files to an existing DeliverySubmission.

    Accepts POST with multipart files in the 'files' field.
    Returns a rendered partial of the updated attachment list.
    """
    submission = get_object_or_404(DeliverySubmission, pk=pk)
    files = request.FILES.getlist("files")

    errors: list[str] = []
    for uploaded_file in files:
        try:
            from core.services.file_service import save_attachment

            save_attachment(
                uploaded_file=uploaded_file,
                content_object=submission,
                file_type="delivery_order",
                uploaded_by=request.user,
            )
        except Exception as exc:
            errors.append(str(exc))
            logger.exception(
                "File upload failed for DeliverySubmission #%s: %s",
                submission.pk,
                exc,
            )

    submission.refresh_from_db()
    return render(
        request,
        "deliveries/_attachment_list.html",
        {
            "submission": submission,
            "upload_errors": errors,
        },
    )


def _get_linkable_purchase_request(request):
    raw_purchase_request_id = request.POST.get("purchase_request") or request.GET.get("purchase_request")
    if not raw_purchase_request_id:
        return None

    from orders.models import PurchaseRequest

    purchase_request = get_object_or_404(
        PurchaseRequest.objects.select_related("requester", "project", "expense_category"),
        pk=raw_purchase_request_id,
    )
    if purchase_request.requester != request.user:
        raise PermissionError
    return purchase_request


def _delivery_initial_from_purchase_request(purchase_request) -> dict:
    if purchase_request is None:
        return {"status": "partially_delivered"}

    remaining_quantity = purchase_request.remaining_quantity or purchase_request.ordered_quantity
    status = "fully_delivered" if remaining_quantity == purchase_request.ordered_quantity else "partially_delivered"
    return {
        "vendor": purchase_request.vendor,
        "currency": purchase_request.currency,
        "delivered_quantity": remaining_quantity,
        "total_price": purchase_request.unit_price * remaining_quantity,
        "status": status,
    }
