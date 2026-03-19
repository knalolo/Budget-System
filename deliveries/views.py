"""Template views for the deliveries app."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
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
    if request.method == "POST":
        form = DeliverySubmissionForm(request.POST)
        files = request.FILES.getlist("files")

        if not files:
            form.add_error(None, "At least one DO/SO document must be attached.")

        if form.is_valid() and files:
            try:
                submission = create_delivery_submission(
                    data=form.cleaned_data,
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
        form = DeliverySubmissionForm()

    return render(
        request,
        "deliveries/form.html",
        {"form": form},
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
