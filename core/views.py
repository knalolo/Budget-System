"""Template views for the core app (dashboard)."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q, Sum
from django.urls import reverse
from django.views.generic import TemplateView

from core.services.exchange_rate_service import convert_amount_to_sgd

logger = logging.getLogger(__name__)

# Statuses that count as "pending approval" for the current user's queue.
_PENDING_STATUSES = ("pending_pcm", "pending_final")
_PAYMENT_DRAFT_STATUSES = ("draft",)
_PAYMENT_SUBMITTED_STATUSES = ("pending_pcm", "pending_final", "approved")
_PAYMENT_ACTIVE_STATUSES = _PAYMENT_DRAFT_STATUSES + _PAYMENT_SUBMITTED_STATUSES

_ZERO_DECIMAL = Decimal("0.00")


def _get_user_profile(user):
    """Return the linked UserProfile, or None if unavailable."""
    try:
        return user.profile
    except AttributeError:
        return None


def _get_user_role(user) -> str:
    """Return the primary role string for *user*, defaulting to 'requester'."""
    profile = _get_user_profile(user)
    return profile.primary_role if profile is not None else "requester"


def _user_can_review_all_requests(user) -> bool:
    """Return True when the dashboard should expose all workflow records."""
    profile = _get_user_profile(user)
    return bool(profile and profile.can_view_all_requests)


def _build_pending_approvals_query(user):
    """
    Return (pr_qs, payment_qs) querysets of items pending the given user's
    approval based on their role. Returns empty querysets for requesters.
    """
    from orders.models import PurchaseRequest
    from payments.models import PaymentRelease

    profile = _get_user_profile(user)
    if profile is None:
        return PurchaseRequest.objects.none(), PaymentRelease.objects.none()

    pr_q = Q()
    payment_q = Q()

    if profile.is_project_approver:
        pr_q |= Q(status="pending_pcm", purchase_type="project")
        payment_q |= Q(status="pending_pcm", purchase_request__purchase_type="project")
    if profile.is_non_project_approver:
        pr_q |= Q(status="pending_pcm", purchase_type="non_project")
        payment_q |= Q(status="pending_pcm", purchase_request__purchase_type="non_project")
    if profile.is_office_approver:
        pr_q |= Q(status="pending_pcm", purchase_type="office")
        payment_q |= Q(status="pending_pcm", purchase_request__purchase_type="office")
    if profile.is_final_approver:
        pr_q |= Q(status="pending_final") | Q(status="cancellation_pending")
        payment_q |= Q(status="pending_final")
    if profile.is_admin:
        pr_q |= Q(status="cancellation_pending")

    pr_qs = PurchaseRequest.objects.filter(pr_q) if pr_q else PurchaseRequest.objects.none()
    payment_qs = PaymentRelease.objects.filter(payment_q) if payment_q else PaymentRelease.objects.none()

    return pr_qs, payment_qs


def _dashboard_purchase_requests_query(user):
    """Return PRs that are still in the purchase-request stage list."""
    from orders.models import PurchaseRequest

    qs = (
        PurchaseRequest.objects.all()
        if _user_can_review_all_requests(user)
        else PurchaseRequest.objects.filter(requester=user)
    )
    return qs.select_related("requester", "project", "expense_category")


def _dashboard_delivery_stage_query(user):
    """Return PRs that are already in the post-approval execution stage."""
    from orders.models import PurchaseRequest

    base_qs = (
        PurchaseRequest.objects.all()
        if _user_can_review_all_requests(user)
        else PurchaseRequest.objects.filter(requester=user)
    )
    purchase_requests = (
        base_qs.select_related("requester", "project", "expense_category")
        .prefetch_related("delivery_submissions", "payment_releases")
        .order_by("-updated_at")
    )
    return [
        purchase_request
        for purchase_request in purchase_requests
        if purchase_request.workflow_stage not in (
            "draft",
            "awaiting_pr_approval",
            "rejected",
            "cancellation_pending",
            "cancelled",
        )
    ]


def _dashboard_execution_stage_query(user):
    """Return execution-stage PRs for requester-side workflow calculations."""
    return _dashboard_delivery_stage_query(user)


def _dashboard_payment_releases_query(user):
    """Return the requester's payment releases."""
    from payments.models import PaymentRelease

    qs = (
        PaymentRelease.objects.all()
        if _user_can_review_all_requests(user)
        else PaymentRelease.objects.filter(requester=user)
    )
    return qs.select_related("requester", "project", "expense_category", "purchase_request")


def _sum_by_currency(qs) -> dict[str, float]:
    """Return a {currency: amount} summary for the supplied queryset."""
    rows = qs.values("currency").annotate(total=Sum("total_price"))
    return {row["currency"]: float(row["total"] or 0) for row in rows}


def _format_spend_summary(spend_by_currency: dict[str, float]) -> str:
    """Return a compact spend summary suitable for dashboard cards."""
    spend_parts = []
    for currency in ("SGD", "USD", "EUR"):
        amount = spend_by_currency.get(currency)
        if amount:
            spend_parts.append(f"{currency} {amount:,.2f}")
    return " / ".join(spend_parts) if spend_parts else "-"


def _approved_pr_spend_this_month(user) -> dict[str, float]:
    """Compute approved PR value for the current month, grouped by currency."""
    from orders.models import PurchaseRequest

    today = date.today()
    qs = PurchaseRequest.objects.filter(
        requester=user,
        status="approved",
        created_at__year=today.year,
        created_at__month=today.month,
    )
    return _sum_by_currency(qs)


def _approved_payment_spend_this_month(user) -> dict[str, float]:
    """
    Compute approved payment-release value for the current month.

    Uses updated_at so the value reflects when the payment was approved.
    """
    from payments.models import PaymentRelease

    today = date.today()
    qs = PaymentRelease.objects.filter(
        requester=user,
        status="approved",
        updated_at__year=today.year,
        updated_at__month=today.month,
    )
    return _sum_by_currency(qs)


def _requester_pending_items_count(user) -> int:
    """Return the count of the requester's current items still under review."""
    pending_prs = _dashboard_purchase_requests_query(user).filter(status__in=_PENDING_STATUSES)
    pending_payments = _dashboard_payment_releases_query(user).filter(status__in=_PENDING_STATUSES)
    return pending_prs.count() + pending_payments.count()


def _requester_ready_for_payment_count(user) -> int:
    return sum(
        1
        for purchase_request in _dashboard_execution_stage_query(user)
        if purchase_request.workflow_stage == "payment_pending"
    )


def _requester_do_pending_count(user) -> int:
    return sum(
        1
        for purchase_request in _dashboard_execution_stage_query(user)
        if purchase_request.workflow_stage in ("ready_for_execution", "goods_pending")
    )


def _requester_partial_delivery_count(user) -> int:
    return sum(
        1
        for purchase_request in _dashboard_execution_stage_query(user)
        if purchase_request.goods_stage == "partially_delivered"
    )


def _requester_do_still_required_payments(user):
    from payments.models import PaymentRelease

    payments = (
        PaymentRelease.objects.filter(
            requester=user,
            status="approved",
            payment_type="advance",
            purchase_request__isnull=False,
        )
        .select_related("purchase_request", "project")
        .order_by("-updated_at")
    )
    return [
        payment
        for payment in payments
        if payment.do_follow_up_required
    ]


def _build_requester_action_items(user):
    action_items = []

    def _requester_name(requester):
        full_name = requester.get_full_name()
        return full_name or requester.username

    def _purchase_request_subtitle(purchase_request):
        return (
            f"{_requester_name(purchase_request.requester)} - "
            f"{purchase_request.vendor} - {purchase_request.project.mc_number}"
        )

    def _payment_subtitle(payment):
        if payment.project_id:
            return (
                f"{_requester_name(payment.requester)} - "
                f"{payment.vendor} - {payment.project.mc_number}"
            )
        return f"{_requester_name(payment.requester)} - {payment.vendor}"

    def _pr_detail_url(purchase_request):
        return reverse("orders:purchase-request-detail", args=[purchase_request.pk])

    def _pr_edit_url(purchase_request):
        return reverse("orders:purchase-request-edit", args=[purchase_request.pk])

    def _delivery_create_url(purchase_request):
        return f"{reverse('deliveries:create')}?purchase_request={purchase_request.pk}"

    def _delivery_update_url(delivery_submission):
        return reverse("deliveries:update", args=[delivery_submission.pk])

    def _delivery_detail_url(delivery_submission):
        return reverse("deliveries:detail", args=[delivery_submission.pk])

    def _payment_create_url(purchase_request):
        payment_type = (
            "standard"
            if purchase_request.delivered_quantity > 0
            else "advance"
        )
        return (
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
            f"&payment_type={payment_type}"
        )

    def _payment_detail_url(payment):
        return reverse("payments:detail", args=[payment.pk])

    def _payment_edit_url(payment):
        return reverse("payments:update", args=[payment.pk])

    def _rejection_comment(obj) -> str:
        if getattr(obj, "final_decision", "") == "rejected" and getattr(obj, "final_comment", ""):
            return obj.final_comment
        if getattr(obj, "pcm_decision", "") == "rejected" and getattr(obj, "pcm_comment", ""):
            return obj.pcm_comment
        return ""

    def _changes_requested_detail(obj, fallback: str) -> str:
        comment = _rejection_comment(obj)
        if comment:
            return f"Changes requested: {comment}"
        return fallback

    def _append_purchase_request_progress_item(purchase_request, *, priority: int):
        latest_payment = purchase_request.latest_payment_release
        submitted_payment = purchase_request.latest_submitted_payment_release
        payment_draft = purchase_request.latest_payment_draft
        open_delivery_submission = purchase_request.latest_open_delivery_submission
        latest_delivery_submission = purchase_request.latest_delivery_submission
        has_submitted_payment = submitted_payment is not None

        if purchase_request.workflow_completed:
            return

        if purchase_request.workflow_stage == "goods_follow_up_required":
            label = "Partial Delivery Follow-up"
            detail = (
                f"Received {purchase_request.delivered_quantity}/{purchase_request.ordered_quantity}. "
                "Keep updating the same Goods recieve record until all goods arrive."
            )
            primary_text = "Continue Goods recieve"
            primary_url = _delivery_update_url(open_delivery_submission)
            if payment_draft:
                secondary_text = "Open Payment Draft"
                secondary_url = _payment_edit_url(payment_draft)
            elif latest_payment is not None:
                secondary_text = "Open Payment"
                secondary_url = _payment_detail_url(latest_payment)
            else:
                secondary_text = "Submit Payment"
                secondary_url = _payment_create_url(purchase_request)
        elif purchase_request.workflow_stage == "payment_pending":
            label = "Payment Still Required"
            detail = (
                "Goods recieve has already been submitted. Submit the payment release next to complete this request."
            )
            primary_text = "Open Payment Draft" if payment_draft else "Submit Payment"
            primary_url = (
                _payment_edit_url(payment_draft)
                if payment_draft
                else _payment_create_url(purchase_request)
            )
            secondary_text = None
            secondary_url = None
        elif purchase_request.workflow_stage == "goods_pending":
            label = "Goods recieve Still Required"
            if payment_draft:
                detail = (
                    "A payment draft already exists for this request. Goods recieve is still required before the workflow can finish."
                )
                secondary_text = "Open Payment Draft"
                secondary_url = _payment_edit_url(payment_draft)
            else:
                detail = (
                    "Payment has already been submitted. Goods recieve is still required to finish this request."
                )
                secondary_text = "Open Payment" if latest_payment is not None else None
                secondary_url = (
                    _payment_detail_url(latest_payment)
                    if latest_payment is not None
                    else None
                )
            primary_text = "Continue Goods recieve" if open_delivery_submission else "Submit Goods recieve"
            primary_url = (
                _delivery_update_url(open_delivery_submission)
                if open_delivery_submission is not None
                else _delivery_create_url(purchase_request)
            )
        elif purchase_request.workflow_stage == "awaiting_payment_approval":
            return
        else:
            label = "Choose Next Step"
            detail = (
                "Approval is complete. You can submit Goods recieve first or submit Payment first. "
                "The request stays open until both have been submitted."
            )
            primary_text = "Continue Goods recieve" if open_delivery_submission else "Submit Goods recieve"
            primary_url = (
                _delivery_update_url(open_delivery_submission)
                if open_delivery_submission is not None
                else _delivery_create_url(purchase_request)
            )
            secondary_text = "Submit Payment"
            secondary_url = _payment_create_url(purchase_request)

        action_items.append(
            {
                "kind": "purchase_request",
                "label": label,
                "title": purchase_request.workflow_number,
                "subtitle": _purchase_request_subtitle(purchase_request),
                "detail": detail,
                "object": purchase_request,
                "priority": priority,
                "primary_text": primary_text,
                "primary_url": primary_url,
                "secondary_text": secondary_text,
                "secondary_url": secondary_url,
                "tertiary_text": "Open PR",
                "tertiary_url": _pr_detail_url(purchase_request),
            }
        )

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status="rejected")
        .select_related("project")
        .order_by("-updated_at")
    ):
        action_items.append(
            {
                "kind": "purchase_request",
                "label": "PR Changes Requested",
                "title": purchase_request.workflow_number,
                "subtitle": _purchase_request_subtitle(purchase_request),
                "detail": _changes_requested_detail(
                    purchase_request,
                    "This purchase request was rejected. Review the comments, edit it, and resubmit for approval.",
                ),
                "object": purchase_request,
                "priority": 0,
                "primary_text": "Edit PR",
                "primary_url": _pr_edit_url(purchase_request),
                "tertiary_text": "Open PR",
                "tertiary_url": _pr_detail_url(purchase_request),
            }
        )

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status="draft")
        .select_related("project")
        .order_by("-updated_at")
    ):
        action_items.append(
            {
                "kind": "purchase_request",
                "label": "Complete Draft PR",
                "title": purchase_request.workflow_number,
                "subtitle": _purchase_request_subtitle(purchase_request),
                "detail": "This purchase request is still in draft. Complete it and submit for approval when ready.",
                "object": purchase_request,
                "priority": 0,
                "primary_text": "Open PR",
                "primary_url": _pr_detail_url(purchase_request),
            }
        )

    for payment in (
        _dashboard_payment_releases_query(user)
        .filter(status="rejected")
        .select_related("project", "purchase_request")
        .order_by("-updated_at")
    ):
        action_items.append(
            {
                "kind": "payment",
                "label": "Payment Release Changes Requested",
                "title": payment.workflow_number,
                "subtitle": _payment_subtitle(payment),
                "detail": _changes_requested_detail(
                    payment,
                    "This payment release was rejected. Review the comments, edit it, and resubmit for approval.",
                ),
                "object": payment,
                "priority": 1,
                "primary_text": "Edit Payment",
                "primary_url": _payment_edit_url(payment),
                "tertiary_text": "Open Payment",
                "tertiary_url": _payment_detail_url(payment),
            }
        )

    for payment in (
        _dashboard_payment_releases_query(user)
        .filter(status="draft", purchase_request__isnull=True)
        .select_related("project", "purchase_request")
        .order_by("-updated_at")
    ):
        subtitle = _payment_subtitle(payment)
        action_items.append(
            {
                "kind": "payment",
                "label": "Complete Payment Draft",
                "title": payment.workflow_number,
                "subtitle": subtitle,
                "detail": "This payment release is still in draft. Review it and submit for approval when ready.",
                "object": payment,
                "priority": 1,
                "primary_text": "Open Payment",
                "primary_url": _payment_edit_url(payment),
            }
        )

    for purchase_request in _dashboard_execution_stage_query(user):
        _append_purchase_request_progress_item(purchase_request, priority=3)

    return sorted(
        action_items,
        key=lambda item: (
            item["priority"],
            -item["object"].updated_at.timestamp(),
        ),
    )


def _build_requester_waiting_items(user):
    waiting_items = []

    def _requester_name(requester):
        full_name = requester.get_full_name()
        return full_name or requester.username

    def _purchase_request_subtitle(purchase_request):
        return (
            f"{_requester_name(purchase_request.requester)} - "
            f"{purchase_request.vendor} - {purchase_request.project.mc_number}"
        )

    def _payment_subtitle(payment):
        if payment.project_id:
            return (
                f"{_requester_name(payment.requester)} - "
                f"{payment.vendor} - {payment.project.mc_number}"
            )
        return f"{_requester_name(payment.requester)} - {payment.vendor}"

    def _approval_waiting_detail(status_label: str, first_role_label: str, *, payment: bool) -> str:
        if status_label == "pending_final":
            return (
                "Waiting for Final approval before payment can proceed."
                if payment
                else "Waiting for Final approval before it can move to the next step."
            )
        return (
            f"Waiting for {first_role_label} review before payment can proceed."
            if payment
            else f"Waiting for {first_role_label} review before it can move to the next step."
        )

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status__in=_PENDING_STATUSES)
        .select_related("project")
        .order_by("-updated_at")
    ):
        waiting_items.append(
            {
                "kind": "purchase_request",
                "label": purchase_request.human_status_label,
                "title": purchase_request.workflow_number,
                "subtitle": _purchase_request_subtitle(purchase_request),
                "detail": _approval_waiting_detail(
                    purchase_request.status,
                    purchase_request.first_approver_role_label,
                    payment=False,
                ),
                "object": purchase_request,
            }
        )

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status="cancellation_pending")
        .select_related("project")
        .order_by("-updated_at")
    ):
        waiting_items.append(
            {
                "kind": "purchase_request",
                "label": "Cancellation Requested",
                "title": purchase_request.workflow_number,
                "subtitle": _purchase_request_subtitle(purchase_request),
                "detail": "Cancellation is waiting for Final Approver review.",
                "object": purchase_request,
            }
        )

    for payment in (
        _dashboard_payment_releases_query(user)
        .filter(status__in=_PENDING_STATUSES)
        .select_related("project", "purchase_request")
        .order_by("-updated_at")
    ):
        waiting_items.append(
            {
                "kind": "payment",
                "label": payment.human_status_label,
                "title": payment.workflow_number,
                "subtitle": _payment_subtitle(payment),
                "detail": _approval_waiting_detail(
                    payment.status,
                    payment.first_approver_role_label,
                    payment=True,
                ),
                "object": payment,
            }
        )

    return sorted(waiting_items, key=lambda item: -item["object"].updated_at.timestamp())


def _empty_project_spend_row(project):
    return {
        "mc_number": project.mc_number,
        "project_name": project.name,
        "amount_sgd": _ZERO_DECIMAL,
    }


def _build_completed_yearly_spend_rows():
    """Return yearly SGD spend summaries for completed PR flows."""
    from orders.models import Project, PurchaseRequest

    projects = list(Project.objects.order_by("mc_number"))
    current_year = date.today().year
    year_buckets: dict[int, dict] = {}

    completed_purchase_requests = (
        PurchaseRequest.objects.select_related("project")
        .prefetch_related("delivery_submissions", "payment_releases")
        .order_by("-created_at")
    )

    def _ensure_year(year: int) -> dict:
        if year not in year_buckets:
            year_buckets[year] = {
                "year": year,
                "projects": {
                    project.mc_number: _empty_project_spend_row(project)
                    for project in projects
                },
                "total_sgd": _ZERO_DECIMAL,
            }
        return year_buckets[year]

    _ensure_year(current_year)

    for purchase_request in completed_purchase_requests:
        if not purchase_request.workflow_completed:
            continue

        year_bucket = _ensure_year(purchase_request.created_at.year)
        try:
            amount_sgd = convert_amount_to_sgd(
                purchase_request.total_price,
                purchase_request.currency,
            )
        except RuntimeError:
            logger.warning(
                "Skipping yearly spend conversion for PR %s because %s -> SGD failed.",
                purchase_request.request_number,
                purchase_request.currency,
            )
            continue
        mc_number = purchase_request.project.mc_number

        if mc_number not in year_bucket["projects"]:
            year_bucket["projects"][mc_number] = {
                "mc_number": mc_number,
                "project_name": purchase_request.project.name,
                "amount_sgd": _ZERO_DECIMAL,
            }

        year_bucket["projects"][mc_number]["amount_sgd"] += amount_sgd
        year_bucket["total_sgd"] += amount_sgd

    yearly_rows = []
    for year in sorted(year_buckets.keys(), reverse=True):
        bucket = year_buckets[year]
        yearly_rows.append(
            {
                "year": year,
                "project_rows": [
                    bucket["projects"][project.mc_number]
                    for project in projects
                    if project.mc_number in bucket["projects"]
                ] + [
                    row
                    for mc_number, row in bucket["projects"].items()
                    if mc_number not in {project.mc_number for project in projects}
                ],
                "total_sgd": bucket["total_sgd"],
            }
        )

    return yearly_rows


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard landing page."""

    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        from deliveries.models import DeliverySubmission
        from orders.models import PurchaseRequest
        from payments.models import PaymentRelease

        my_purchase_requests_qs = _dashboard_purchase_requests_query(user)
        my_purchase_requests = my_purchase_requests_qs.order_by("-created_at")[:10]
        my_delivery_stage_requests_qs = _dashboard_delivery_stage_query(user)
        my_delivery_stage_requests = sorted(
            my_delivery_stage_requests_qs,
            key=lambda purchase_request: purchase_request.updated_at,
            reverse=True,
        )[:10]
        my_payment_releases_qs = _dashboard_payment_releases_query(user)
        my_payment_releases = my_payment_releases_qs.order_by("-created_at")[:10]

        pr_pending_qs, payment_pending_qs = _build_pending_approvals_query(user)

        pr_pending = (
            pr_pending_qs
            .select_related("requester", "project")
            .order_by("-created_at")[:20]
        )
        payment_pending = (
            payment_pending_qs
            .select_related("requester", "project", "purchase_request")
            .order_by("-created_at")[:20]
        )

        pending_approvals_count = pr_pending_qs.count() + payment_pending_qs.count()

        today = date.today()
        profile = _get_user_profile(user)
        user_role = _get_user_role(user)
        is_approver = _user_can_review_all_requests(user)

        total_prs = (
            PurchaseRequest.objects.count()
            if is_approver
            else PurchaseRequest.objects.filter(requester=user).count()
        )
        approved_prs = PurchaseRequest.objects.filter(
            requester=user, status="approved"
        ).count()
        pending_prs = PurchaseRequest.objects.filter(
            requester=user, status__in=_PENDING_STATUSES
        ).count()

        total_payments = PaymentRelease.objects.filter(requester=user).count()
        approved_payments = PaymentRelease.objects.filter(
            requester=user, status="approved"
        ).count()

        total_deliveries = DeliverySubmission.objects.filter(requester=user).count()
        dashboard_prs_count = my_purchase_requests_qs.count()
        dashboard_payments_count = my_payment_releases_qs.count()

        approved_this_month = PurchaseRequest.objects.filter(
            requester=user,
            status="approved",
            created_at__year=today.year,
            created_at__month=today.month,
        ).count()

        requester_pending_count = _requester_pending_items_count(user)
        requester_ready_for_payment_count = _requester_ready_for_payment_count(user)
        requester_do_pending_count = _requester_do_pending_count(user)
        requester_partial_delivery_count = _requester_partial_delivery_count(user)
        requester_do_still_required_payments = _requester_do_still_required_payments(user)
        requester_action_items = _build_requester_action_items(user)
        requester_waiting_items = _build_requester_waiting_items(user)

        pr_spend_by_currency = _approved_pr_spend_this_month(user)
        payment_spend_by_currency = _approved_payment_spend_this_month(user)
        total_spend_display = _format_spend_summary(pr_spend_by_currency)
        approved_payment_spend_display = _format_spend_summary(payment_spend_by_currency)
        approver_yearly_spend_rows = _build_completed_yearly_spend_rows() if is_approver else []

        stats = {
            "total_prs": total_prs,
            "approved_prs": approved_prs,
            "pending_prs": pending_prs,
            "total_payments": total_payments,
            "approved_payments": approved_payments,
            "total_deliveries": total_deliveries,
            "dashboard_prs_count": dashboard_prs_count,
            "dashboard_payments_count": dashboard_payments_count,
            "dashboard_deliveries_count": len(my_delivery_stage_requests_qs),
            "approved_this_month": approved_this_month,
            "total_spend_display": total_spend_display,
            "spend_by_currency": pr_spend_by_currency,
            "requester_pending_count": requester_pending_count,
            "requester_ready_for_payment_count": requester_ready_for_payment_count,
            "requester_do_pending_count": requester_do_pending_count,
            "requester_partial_delivery_count": requester_partial_delivery_count,
            "requester_do_still_required_count": len(requester_do_still_required_payments),
            "approved_payment_spend_display": approved_payment_spend_display,
            "approved_payment_spend_by_currency": payment_spend_by_currency,
            "approver_yearly_spend_rows": approver_yearly_spend_rows,
        }

        context.update(
            {
                "my_purchase_requests": my_purchase_requests,
                "my_delivery_stage_requests": my_delivery_stage_requests,
                "my_payment_releases": my_payment_releases,
                "pr_pending_approvals": pr_pending,
                "payment_pending_approvals": payment_pending,
                "pending_approvals_count": pending_approvals_count,
                "stats": stats,
                "is_approver": is_approver,
                "user_role": user_role,
                "requester_do_still_required_payments": requester_do_still_required_payments[:5],
                "requester_action_items": requester_action_items[:8],
                "requester_waiting_items": requester_waiting_items[:8],
            }
        )
        return context

