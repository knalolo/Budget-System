"""Template views for the deliveries app."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView

from core.services.workflow_delete_service import delete_delivery_workflow

from .forms import DeliverySubmissionForm
from .models import DeliverySubmission
from .services import create_delivery_submission, update_delivery_submission

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
        )
        if _user_can_view_all_submissions(self.request.user):
            qs = qs.all()
        else:
            qs = qs.filter(requester=self.request.user)
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
        ctx["can_create_delivery_submission"] = not _is_approval_only_role(self.request.user)
        ctx["is_admin"] = _is_admin(self.request.user)
        return ctx


class DeliverySubmissionCreateView(LoginRequiredMixin, object):
    """Create a delivery submission (submit immediately)."""

    pass


@login_required
def delivery_submission_create(request):
    """Handle GET (render form) and POST (create submission) for delivery submissions."""
    if _is_approval_only_role(request.user):
        return HttpResponseForbidden(
            "Purchase Type approver and Final Approver accounts cannot create goods recieve records."
        )
    try:
        source_purchase_request = _get_linkable_purchase_request(request)
    except PermissionError:
        return HttpResponseForbidden("You do not have permission to use this purchase request.")

    existing_open_submission = _get_editable_delivery_submission(request.user, source_purchase_request)
    if existing_open_submission is not None:
        messages.info(
            request,
            f"Continue updating {existing_open_submission.workflow_number} until all goods are received.",
        )
        if request.method == "GET":
            return redirect("deliveries:update", pk=existing_open_submission.pk)
        if request.method == "POST":
            return redirect("deliveries:update", pk=existing_open_submission.pk)

    if request.method == "POST":
        form = DeliverySubmissionForm(
            request.POST,
            source_purchase_request=source_purchase_request,
        )
        files = request.FILES.getlist("files")

        if not files:
            form.add_error(None, "At least one DO/SO document must be attached.")

        if form.is_valid() and files:
            try:
                submission = create_delivery_submission(
                    data={
                        **form.cleaned_data,
                        "line_items": form.parsed_line_items,
                        "purchase_request": source_purchase_request,
                    },
                    user=request.user,
                    files=files,
                )
                messages.success(request, f"Goods recieve record {submission.workflow_number} created successfully.")
                return redirect("deliveries:detail", pk=submission.pk)
            except Exception:
                logger.exception("Failed to create delivery submission.")
                messages.error(
                    request,
                    "An unexpected error occurred. Please try again.",
                )
    else:
        form = DeliverySubmissionForm(
            initial=_delivery_initial_from_purchase_request(source_purchase_request),
            source_purchase_request=source_purchase_request,
        )

    return render(
        request,
        "deliveries/form.html",
        {
            "form": form,
            "source_purchase_request": source_purchase_request,
            "is_edit": False,
        },
    )


@login_required
def delivery_submission_update(request, pk: int):
    """Continue a partially delivered goods receive record until goods are complete."""
    submission = get_object_or_404(
        DeliverySubmission.objects.select_related("purchase_request", "requester")
        .prefetch_related("attachments", "line_items"),
        pk=pk,
    )

    if not _can_manage_submission(request.user, submission):
        return HttpResponseForbidden("Only the requester or admin can edit this goods recieve record.")

    if not submission.can_continue_receiving:
        messages.info(request, "This goods recieve record is already complete and no longer needs updates.")
        return redirect("deliveries:detail", pk=submission.pk)

    source_purchase_request = submission.purchase_request
    existing_attachment_count = submission.attachments.count()

    if request.method == "POST":
        form = DeliverySubmissionForm(
            request.POST,
            instance=submission,
            source_purchase_request=source_purchase_request,
        )
        files = request.FILES.getlist("files")

        if existing_attachment_count == 0 and not files:
            form.add_error(None, "At least one DO/SO document must be attached.")

        if form.is_valid() and (existing_attachment_count > 0 or files):
            try:
                updated_submission = update_delivery_submission(
                    submission=submission,
                    data={
                        **form.cleaned_data,
                        "line_items": form.parsed_line_items,
                        "purchase_request": source_purchase_request,
                    },
                    user=request.user,
                    files=files,
                )
                if updated_submission.is_fully_delivered:
                    messages.success(
                        request,
                        f"Goods recieve record {updated_submission.workflow_number} is now fully delivered.",
                    )
                else:
                    messages.success(
                        request,
                        f"Goods recieve record {updated_submission.workflow_number} updated. Continue until all goods arrive.",
                    )
                return redirect("deliveries:detail", pk=updated_submission.pk)
            except Exception:
                logger.exception("Failed to update delivery submission.")
                messages.error(
                    request,
                    "An unexpected error occurred. Please try again.",
                )
    else:
        form = DeliverySubmissionForm(
            instance=submission,
            source_purchase_request=source_purchase_request,
        )

    return render(
        request,
        "deliveries/form.html",
        {
            "form": form,
            "source_purchase_request": source_purchase_request,
            "submission": submission,
            "is_edit": True,
        },
    )


class DeliverySubmissionDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single delivery submission."""

    model = DeliverySubmission
    template_name = "deliveries/detail.html"
    context_object_name = "submission"

    def get_queryset(self):
        qs = DeliverySubmission.objects.select_related(
            "requester", "purchase_request"
        ).prefetch_related("attachments")
        if _user_can_view_all_submissions(self.request.user):
            return qs
        return qs.filter(requester=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submission = self.object
        linked_purchase_request = submission.purchase_request
        can_manage_submission = _can_manage_submission(self.request.user, submission)
        can_delete = _can_delete_submission(self.request.user, submission)
        context["linked_purchase_request"] = linked_purchase_request
        context["can_delete"] = can_delete
        context["can_manage_submission"] = can_manage_submission
        context["can_create_payment_release"] = bool(
            can_manage_submission
            and linked_purchase_request
            and linked_purchase_request.is_ready_for_payment
        )
        context["can_continue_submission"] = bool(
            can_manage_submission and submission.can_continue_receiving
        )
        context["show_locked_notice"] = bool(
            submission.requester == self.request.user
            and not _is_admin(self.request.user)
            and not submission.requester_can_delete
        )
        if context["can_continue_submission"]:
            context["delivery_submission_update_url"] = reverse(
                "deliveries:update",
                kwargs={"pk": submission.pk},
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
    if not _can_manage_submission(request.user, submission):
        return HttpResponseForbidden("Only the requester or admin can upload goods recieve attachments.")
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


@login_required
def delivery_submission_delete(request, pk: int):
    """Delete a delivery submission created by the current requester."""
    submission = get_object_or_404(DeliverySubmission, pk=pk)

    if request.method != "POST":
        return redirect("deliveries:detail", pk=pk)

    if submission.requester != request.user and not _is_admin(request.user):
        return HttpResponseForbidden("You do not have permission to delete this goods recieve record.")

    if not _is_admin(request.user) and not submission.requester_can_delete:
        return HttpResponseForbidden(
            "This goods recieve record can no longer be deleted because the Purchase Type Approver "
            "or Final Approver has already acted on the linked payment flow."
        )

    request_number = submission.workflow_number
    linked_purchase_request_id = submission.purchase_request_id
    if _is_admin(request.user):
        delete_delivery_workflow(submission)
    else:
        submission.delete()

    if _is_admin(request.user):
        messages.success(request, f"Workflow {request_number} deleted.")
    else:
        messages.success(request, f"Goods recieve record {request_number} deleted.")

    if linked_purchase_request_id and not _is_admin(request.user):
        return redirect("orders:purchase-request-detail", pk=linked_purchase_request_id)
    return redirect("deliveries:list")


def _get_linkable_purchase_request(request):
    raw_purchase_request_id = request.POST.get("purchase_request") or request.GET.get("purchase_request")
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


def _user_can_view_all_submissions(user) -> bool:
    profile = _get_profile(user)
    return bool(profile and profile.can_view_all_requests)


def _can_manage_submission(user, submission: DeliverySubmission) -> bool:
    return submission.requester == user or _is_admin(user)


def _can_delete_submission(user, submission: DeliverySubmission) -> bool:
    if _is_admin(user):
        return True
    return submission.requester == user and submission.requester_can_delete


def _get_editable_delivery_submission(user, purchase_request):
    if purchase_request is None:
        return None

    queryset = purchase_request.delivery_submissions.filter(status="partially_delivered")
    if not _is_admin(user):
        queryset = queryset.filter(requester=user)
    return queryset.order_by("-created_at").first()


def _delivery_initial_from_purchase_request(purchase_request) -> dict:
    if purchase_request is None:
        return {"status": "partially_delivered"}

    remaining_quantity = purchase_request.remaining_quantity or purchase_request.ordered_quantity
    return {
        "vendor": purchase_request.vendor,
        "currency": purchase_request.currency,
        "delivered_quantity": remaining_quantity,
        "total_price": purchase_request.unit_price * remaining_quantity,
        "status": "fully_delivered",
    }
