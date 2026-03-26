"""Template views for the core app (dashboard)."""
from __future__ import annotations

import logging
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Q, Sum
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
    """Return PRs that are still in the purchase-request stage."""
    from orders.models import PurchaseRequest
    from payments.models import PaymentRelease

    payment_exists = PaymentRelease.objects.filter(purchase_request=OuterRef("pk"))
    return PurchaseRequest.objects.filter(requester=user).annotate(
        has_payment_release=Exists(payment_exists)
    ).filter(has_payment_release=False)


def _dashboard_payment_releases_query(user):
    """Return payments that have not yet advanced into the delivery stage."""
    from deliveries.models import DeliverySubmission
    from payments.models import PaymentRelease

    delivery_exists = DeliverySubmission.objects.filter(
        purchase_request=OuterRef("purchase_request_id")
    )
    return PaymentRelease.objects.filter(requester=user).annotate(
        has_delivery_submission=Exists(delivery_exists)
    ).filter(
        Q(purchase_request__isnull=True) | Q(has_delivery_submission=False)
    )


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


def _requester_next_step_items_count(user) -> int:
    """
    Return the count of items ready for the requester's next action.

    This covers:
    - PRs that are approved / PO sent / ordered, but not yet moved into payments
    - Payment releases that are approved, but not yet moved into deliveries
    """
    ready_prs = _dashboard_purchase_requests_query(user).filter(
        status__in=("approved", "po_sent", "ordered")
    )
    ready_payments = _dashboard_payment_releases_query(user).filter(status="approved")
    return ready_prs.count() + ready_payments.count()


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
        my_purchase_requests = (
            my_purchase_requests_qs
            .select_related("project", "expense_category")
            .order_by("-created_at")[:10]
        )
        my_payment_releases_qs = _dashboard_payment_releases_query(user)
        my_payment_releases = (
            my_payment_releases_qs
            .select_related("project", "expense_category")
            .order_by("-created_at")[:10]
        )
        my_delivery_submissions = (
            DeliverySubmission.objects.filter(requester=user)
            .order_by("-created_at")[:5]
        )

        pr_pending_qs, payment_pending_qs = _build_pending_approvals_query(user)

        pr_pending = (
            pr_pending_qs
            .select_related("requester", "project")
            .order_by("-created_at")[:20]
        )
        payment_pending = (
            payment_pending_qs
            .select_related("requester", "project")
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
        requester_next_step_count = _requester_next_step_items_count(user)

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
            "approved_this_month": approved_this_month,
            "total_spend_display": total_spend_display,
            "spend_by_currency": pr_spend_by_currency,
            "requester_pending_count": requester_pending_count,
            "requester_next_step_count": requester_next_step_count,
            "approved_payment_spend_display": approved_payment_spend_display,
            "approved_payment_spend_by_currency": payment_spend_by_currency,
        }

        user_role = _get_user_role(user)
        is_approver = user_role in _ALL_APPROVER_ROLES

        context.update(
            {
                "my_purchase_requests": my_purchase_requests,
                "my_payment_releases": my_payment_releases,
                "my_delivery_submissions": my_delivery_submissions,
                "pr_pending_approvals": pr_pending,
                "payment_pending_approvals": payment_pending,
                "pending_approvals_count": pending_approvals_count,
                "stats": stats,
                "is_approver": is_approver,
                "user_role": user_role,
            }
        )
        return context
