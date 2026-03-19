"""Template views for the core app (dashboard)."""
from __future__ import annotations

import logging
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
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
    approval based on their role.  Returns empty querysets for requesters.
    """
    from orders.models import PurchaseRequest
    from payments.models import PaymentRelease

    role = _get_user_role(user)

    if role in _PCM_APPROVER_ROLES and role in _FINAL_APPROVER_ROLES:
        # admin: sees all pending items
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


def _total_spend_this_month(user) -> dict[str, float]:
    """
    Compute total approved spend for this calendar month, grouped by currency.
    Returns a dict of {currency: amount}.
    """
    from orders.models import PurchaseRequest

    today = date.today()
    qs = PurchaseRequest.objects.filter(
        requester=user,
        status="approved",
        created_at__year=today.year,
        created_at__month=today.month,
    )
    rows = qs.values("currency").annotate(total=Sum("total_price"))
    return {row["currency"]: float(row["total"] or 0) for row in rows}


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard landing page."""

    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Lazy imports to avoid circular imports at module level.
        from deliveries.models import DeliverySubmission
        from orders.models import PurchaseRequest
        from payments.models import PaymentRelease

        # ------------------------------------------------------------------
        # Recent activity for the current user
        # ------------------------------------------------------------------
        my_purchase_requests = (
            PurchaseRequest.objects.filter(requester=user)
            .select_related("project", "expense_category")
            .order_by("-created_at")[:10]
        )
        my_payment_releases = (
            PaymentRelease.objects.filter(requester=user)
            .select_related("project", "expense_category")
            .order_by("-created_at")[:10]
        )
        my_delivery_submissions = (
            DeliverySubmission.objects.filter(requester=user)
            .order_by("-created_at")[:5]
        )

        # ------------------------------------------------------------------
        # Pending approvals queue
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Summary statistics
        # ------------------------------------------------------------------
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

        # Approved PRs this month (all currencies, for headline count)
        approved_this_month = PurchaseRequest.objects.filter(
            requester=user,
            status="approved",
            created_at__year=today.year,
            created_at__month=today.month,
        ).count()

        spend_by_currency = _total_spend_this_month(user)

        # Build a human-readable spend summary (primary currency first)
        spend_parts = []
        for currency in ("SGD", "USD", "EUR"):
            amount = spend_by_currency.get(currency)
            if amount:
                spend_parts.append(f"{currency} {amount:,.2f}")
        total_spend_display = " / ".join(spend_parts) if spend_parts else "—"

        stats = {
            "total_prs": total_prs,
            "approved_prs": approved_prs,
            "pending_prs": pending_prs,
            "total_payments": total_payments,
            "approved_payments": approved_payments,
            "total_deliveries": total_deliveries,
            "approved_this_month": approved_this_month,
            "total_spend_display": total_spend_display,
            "spend_by_currency": spend_by_currency,
        }

        # ------------------------------------------------------------------
        # Role flags for template rendering
        # ------------------------------------------------------------------
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
