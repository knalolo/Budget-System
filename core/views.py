"""Template views for the core app (dashboard)."""
from __future__ import annotations

import logging
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q, Sum
from django.urls import reverse
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)

# Statuses that count as "pending approval" for the current user's queue.
_PENDING_STATUSES = ("pending_pcm", "pending_final")

# Roles that have approval responsibilities.
_PCM_APPROVER_ROLES = {"pcm_approver", "admin"}
_FINAL_APPROVER_ROLES = {"final_approver", "admin"}
_ALL_APPROVER_ROLES = _PCM_APPROVER_ROLES | _FINAL_APPROVER_ROLES


def _get_user_role(user) -> str:
    """Return the role string for *user*, defaulting to 'requester'."""
    try:
        return user.profile.role
    except AttributeError:
        return "requester"


def _build_pending_approvals_query(user):
    """
    Return (pr_qs, payment_qs) querysets of items pending the given user's
    approval based on their role. Returns empty querysets for requesters.
    """
    from orders.models import PurchaseRequest
    from payments.models import PaymentRelease

    role = _get_user_role(user)

    if role in _PCM_APPROVER_ROLES and role in _FINAL_APPROVER_ROLES:
        pr_qs = PurchaseRequest.objects.filter(
            status__in=_PENDING_STATUSES
        ).exclude(requester=user)
        payment_qs = PaymentRelease.objects.filter(
            status__in=_PENDING_STATUSES
        ).exclude(requester=user)
    elif role in _PCM_APPROVER_ROLES:
        pr_qs = PurchaseRequest.objects.filter(
            status="pending_pcm"
        ).exclude(requester=user)
        payment_qs = PaymentRelease.objects.filter(
            status="pending_pcm"
        ).exclude(requester=user)
    elif role in _FINAL_APPROVER_ROLES:
        pr_qs = PurchaseRequest.objects.filter(
            status="pending_final"
        ).exclude(requester=user)
        payment_qs = PaymentRelease.objects.filter(
            status="pending_final"
        ).exclude(requester=user)
    else:
        pr_qs = PurchaseRequest.objects.none()
        payment_qs = PaymentRelease.objects.none()

    return pr_qs, payment_qs


def _dashboard_purchase_requests_query(user):
    """Return PRs that are still in the pre-delivery purchase-request stage."""
    from orders.models import PurchaseRequest

    return PurchaseRequest.objects.filter(
        requester=user,
    ).exclude(status="ordered")


def _dashboard_delivery_stage_query(user):
    """Return ordered PRs that are now in delivery tracking stage."""
    from orders.models import PurchaseRequest

    return PurchaseRequest.objects.filter(
        requester=user,
        status="ordered",
    ).select_related("project", "expense_category")


def _dashboard_payment_releases_query(user):
    """Return the requester's payment releases."""
    from payments.models import PaymentRelease

    return PaymentRelease.objects.filter(requester=user)


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
    return " / ".join(spend_parts) if spend_parts else "—"


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
        for purchase_request in _dashboard_delivery_stage_query(user)
        if (
            purchase_request.is_ready_for_payment
            and purchase_request.remaining_quantity == 0
            and not purchase_request.payment_releases.filter(payment_type="standard").exists()
        )
    )


def _requester_do_pending_count(user) -> int:
    return sum(
        1
        for purchase_request in _dashboard_delivery_stage_query(user)
        if purchase_request.delivered_quantity == 0
    )


def _requester_partial_delivery_count(user) -> int:
    return sum(
        1
        for purchase_request in _dashboard_delivery_stage_query(user)
        if purchase_request.delivered_quantity > 0 and purchase_request.remaining_quantity > 0
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
    covered_purchase_request_ids = set()

    def _pr_detail_url(purchase_request):
        return reverse("orders:purchase-request-detail", args=[purchase_request.pk])

    def _delivery_create_url(purchase_request):
        return f"{reverse('deliveries:create')}?purchase_request={purchase_request.pk}"

    def _delivery_detail_url(delivery_submission):
        return reverse("deliveries:detail", args=[delivery_submission.pk])

    def _payment_create_url(purchase_request):
        return f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"

    def _advance_payment_create_url(purchase_request):
        return (
            f"{reverse('payments:create')}?purchase_request={purchase_request.pk}"
            "&payment_type=advance"
        )

    def _payment_detail_url(payment):
        return reverse("payments:detail", args=[payment.pk])

    def _payment_edit_url(payment):
        return reverse("payments:update", args=[payment.pk])

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
                "title": purchase_request.request_number,
                "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                "detail": "This purchase request is still in draft. Complete it and submit for approval when ready.",
                "object": purchase_request,
                "priority": 0,
                "primary_text": "Open PR",
                "primary_url": _pr_detail_url(purchase_request),
            }
        )

    for payment in (
        _dashboard_payment_releases_query(user)
        .filter(status="draft")
        .select_related("project", "purchase_request")
        .order_by("-updated_at")
    ):
        subtitle = (
            f"{payment.vendor} · {payment.project.mc_number}"
            if payment.project_id
            else payment.vendor
        )
        action_items.append(
            {
                "kind": "payment",
                "label": "Complete Payment Draft",
                "title": payment.request_number,
                "subtitle": subtitle,
                "detail": "This payment release is still in draft. Review it and submit for approval when ready.",
                "object": payment,
                "priority": 1,
                "primary_text": "Open Payment",
                "primary_url": _payment_edit_url(payment),
            }
        )

    for payment in _requester_do_still_required_payments(user):
        if payment.purchase_request_id:
            covered_purchase_request_ids.add(payment.purchase_request_id)
        latest_delivery = payment.purchase_request.latest_delivery_submission
        action_items.append(
            {
                "kind": "payment",
                "label": "DO Still Required",
                "title": payment.request_number,
                "subtitle": f"{payment.vendor} · {payment.project.mc_number}",
                "detail": (
                    f"Advance payment approved. Goods recieve is still outstanding: "
                    f"{payment.purchase_request.delivered_quantity}/{payment.purchase_request.ordered_quantity} received."
                ),
                "object": payment,
                "priority": 2,
                "primary_text": "Open Goods recieve" if latest_delivery else "Create Goods recieve",
                "primary_url": (
                    _delivery_detail_url(latest_delivery)
                    if latest_delivery
                    else _delivery_create_url(payment.purchase_request)
                ),
                "secondary_text": "Open Payment",
                "secondary_url": _payment_detail_url(payment),
            }
        )

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status__in=("approved", "po_sent"))
        .select_related("project")
        .order_by("-updated_at")
    ):
        if purchase_request.status == "approved" and purchase_request.po_required:
            label = "Choose Next Step"
            detail = (
                "Approval is complete. Continue with the standard path by marking the PO as sent, "
                "or create an advance payment if the supplier requires prepayment."
            )
            primary_text = "Mark PO Sent"
            primary_url = reverse(
                "orders:purchase-request-mark-po-sent",
                args=[purchase_request.pk],
            )
        else:
            label = "Choose Next Step"
            detail = (
                "Approval is complete. Continue with the standard path by opening the Goods recieve form, "
                "or request an advance payment first."
            )
            primary_text = "Track Goods recieve"
            primary_url = _delivery_create_url(purchase_request)

        action_items.append(
            {
                "kind": "purchase_request",
                "label": label,
                "title": purchase_request.request_number,
                "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                "detail": detail,
                "object": purchase_request,
                "priority": 3,
                "primary_text": primary_text,
                "primary_url": primary_url,
                "secondary_text": "Request Advance Payment",
                "secondary_url": _advance_payment_create_url(purchase_request),
                "tertiary_text": "Open PR",
                "tertiary_url": _pr_detail_url(purchase_request),
            }
        )

    for purchase_request in _dashboard_delivery_stage_query(user):
        if purchase_request.pk in covered_purchase_request_ids:
            continue
        if purchase_request.is_ready_for_payment and purchase_request.remaining_quantity == 0:
            action_items.append(
                {
                    "kind": "purchase_request",
                    "label": "Ready For Payment",
                    "title": purchase_request.request_number,
                    "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                    "detail": "Goods recieve is complete. You can create the payment release now.",
                    "object": purchase_request,
                    "priority": 4,
                    "primary_text": "Create Payment",
                    "primary_url": _payment_create_url(purchase_request),
                    "secondary_text": "Open PR",
                    "secondary_url": _pr_detail_url(purchase_request),
                }
            )
        elif purchase_request.delivered_quantity == 0:
            latest_delivery = purchase_request.latest_delivery_submission
            action_items.append(
                {
                    "kind": "purchase_request",
                    "label": "Create Goods recieve",
                    "title": purchase_request.request_number,
                    "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                    "detail": "No Goods recieve has been recorded yet. Follow up and submit DO once goods arrive.",
                    "object": purchase_request,
                    "priority": 5,
                    "primary_text": "Open Goods recieve" if latest_delivery else "Create Goods recieve",
                    "primary_url": (
                        _delivery_detail_url(latest_delivery)
                        if latest_delivery
                        else _delivery_create_url(purchase_request)
                    ),
                    "secondary_text": "Open PR",
                    "secondary_url": _pr_detail_url(purchase_request),
                }
            )
        elif purchase_request.remaining_quantity > 0:
            latest_delivery = purchase_request.latest_delivery_submission
            action_items.append(
                {
                    "kind": "purchase_request",
                    "label": "Partial Delivery Follow-up",
                    "title": purchase_request.request_number,
                    "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                    "detail": (
                        f"Received {purchase_request.delivered_quantity}/{purchase_request.ordered_quantity}. "
                        f"Keep tracking the remaining quantity."
                    ),
                    "object": purchase_request,
                    "priority": 6,
                    "primary_text": "Open Goods recieve" if latest_delivery else "Create Goods recieve",
                    "primary_url": (
                        _delivery_detail_url(latest_delivery)
                        if latest_delivery
                        else _delivery_create_url(purchase_request)
                    ),
                    "secondary_text": "Open PR",
                    "secondary_url": _pr_detail_url(purchase_request),
                }
            )

    return sorted(
        action_items,
        key=lambda item: (
            item["priority"],
            -item["object"].updated_at.timestamp(),
        ),
    )


def _build_requester_waiting_items(user):
    waiting_items = []

    for purchase_request in (
        _dashboard_purchase_requests_query(user)
        .filter(status__in=_PENDING_STATUSES)
        .select_related("project")
        .order_by("-updated_at")
    ):
        waiting_items.append(
            {
                "kind": "purchase_request",
                "label": purchase_request.get_status_display(),
                "title": purchase_request.request_number,
                "subtitle": f"{purchase_request.vendor} · {purchase_request.project.mc_number}",
                "detail": "Waiting for PCM / Final approval before it can move to the next step.",
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
                "label": payment.get_status_display(),
                "title": payment.request_number,
                "subtitle": f"{payment.vendor} · {payment.project.mc_number}",
                "detail": "Waiting for PCM / Final approval before payment can proceed.",
                "object": payment,
            }
        )

    return sorted(waiting_items, key=lambda item: -item["object"].updated_at.timestamp())


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
        my_purchase_requests = my_purchase_requests_qs.select_related(
            "project", "expense_category"
        ).order_by("-created_at")[:10]
        my_delivery_stage_requests_qs = _dashboard_delivery_stage_query(user)
        my_delivery_stage_requests = my_delivery_stage_requests_qs.order_by("-updated_at")[:10]
        my_payment_releases_qs = _dashboard_payment_releases_query(user)
        my_payment_releases = my_payment_releases_qs.select_related(
            "project", "expense_category", "purchase_request"
        ).order_by("-created_at")[:10]

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
        total_prs = PurchaseRequest.objects.filter(requester=user).count()
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

        stats = {
            "total_prs": total_prs,
            "approved_prs": approved_prs,
            "pending_prs": pending_prs,
            "total_payments": total_payments,
            "approved_payments": approved_payments,
            "total_deliveries": total_deliveries,
            "dashboard_prs_count": dashboard_prs_count,
            "dashboard_payments_count": dashboard_payments_count,
            "dashboard_deliveries_count": my_delivery_stage_requests_qs.count(),
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
        }

        user_role = _get_user_role(user)
        is_approver = user_role in _ALL_APPROVER_ROLES

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
