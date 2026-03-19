"""DRF API views for the dashboard data endpoints."""
from __future__ import annotations

import logging
from datetime import date

from django.db.models import Q, Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

_PENDING_STATUSES = ("pending_pcm", "pending_final")
_PCM_APPROVER_ROLES = {"pcm_approver", "admin"}
_FINAL_APPROVER_ROLES = {"final_approver", "admin"}
_ALL_APPROVER_ROLES = _PCM_APPROVER_ROLES | _FINAL_APPROVER_ROLES


def _get_user_role(user) -> str:
    """Return the role string for *user*, defaulting to 'requester'."""
    try:
        return user.profile.role
    except AttributeError:
        return "requester"


def _pending_approval_counts(user) -> dict[str, int]:
    """Return a dict with pr_count and payment_count for items awaiting approval."""
    from orders.models import PurchaseRequest
    from payments.models import PaymentRelease

    role = _get_user_role(user)

    if role in _PCM_APPROVER_ROLES and role in _FINAL_APPROVER_ROLES:
        pr_count = PurchaseRequest.objects.filter(
            status__in=_PENDING_STATUSES
        ).exclude(requester=user).count()
        payment_count = PaymentRelease.objects.filter(
            status__in=_PENDING_STATUSES
        ).exclude(requester=user).count()
    elif role in _PCM_APPROVER_ROLES:
        pr_count = PurchaseRequest.objects.filter(
            status="pending_pcm"
        ).exclude(requester=user).count()
        payment_count = PaymentRelease.objects.filter(
            status="pending_pcm"
        ).exclude(requester=user).count()
    elif role in _FINAL_APPROVER_ROLES:
        pr_count = PurchaseRequest.objects.filter(
            status="pending_final"
        ).exclude(requester=user).count()
        payment_count = PaymentRelease.objects.filter(
            status="pending_final"
        ).exclude(requester=user).count()
    else:
        pr_count = 0
        payment_count = 0

    return {"pr_count": pr_count, "payment_count": payment_count}


class DashboardSummaryView(APIView):
    """
    GET /api/v1/dashboard/summary/

    Returns aggregate statistics for the requesting user:
      - counts by status for PRs, payments, deliveries
      - total spend this month grouped by currency
      - pending approvals count (role-dependent)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        from deliveries.models import DeliverySubmission
        from orders.models import PurchaseRequest
        from payments.models import PaymentRelease

        today = date.today()

        # Purchase request counts
        pr_base = PurchaseRequest.objects.filter(requester=user)
        pr_counts = {
            "total": pr_base.count(),
            "draft": pr_base.filter(status="draft").count(),
            "pending": pr_base.filter(status__in=_PENDING_STATUSES).count(),
            "approved": pr_base.filter(status="approved").count(),
            "rejected": pr_base.filter(status="rejected").count(),
        }

        # Payment release counts
        payment_base = PaymentRelease.objects.filter(requester=user)
        payment_counts = {
            "total": payment_base.count(),
            "draft": payment_base.filter(status="draft").count(),
            "pending": payment_base.filter(status__in=_PENDING_STATUSES).count(),
            "approved": payment_base.filter(status="approved").count(),
            "rejected": payment_base.filter(status="rejected").count(),
        }

        # Delivery counts
        delivery_base = DeliverySubmission.objects.filter(requester=user)
        delivery_counts = {
            "total": delivery_base.count(),
            "submitted": delivery_base.filter(status="submitted").count(),
            "saved": delivery_base.filter(status="saved").count(),
        }

        # Spend this month (approved PRs only)
        spend_rows = (
            pr_base.filter(
                status="approved",
                created_at__year=today.year,
                created_at__month=today.month,
            )
            .values("currency")
            .annotate(total=Sum("total_price"))
        )
        spend_this_month = {
            row["currency"]: float(row["total"] or 0) for row in spend_rows
        }

        # Pending approval counts (role-aware)
        approval_counts = _pending_approval_counts(user)
        pending_approvals_total = (
            approval_counts["pr_count"] + approval_counts["payment_count"]
        )

        data = {
            "purchase_requests": pr_counts,
            "payment_releases": payment_counts,
            "deliveries": delivery_counts,
            "spend_this_month": spend_this_month,
            "pending_approvals": {
                "total": pending_approvals_total,
                "purchase_requests": approval_counts["pr_count"],
                "payment_releases": approval_counts["payment_count"],
            },
        }
        return Response(data)


class MyRequestsView(APIView):
    """
    GET /api/v1/dashboard/my-requests/

    Returns the current user's recent requests across all types (last 10 each).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        from deliveries.models import DeliverySubmission
        from orders.models import PurchaseRequest
        from payments.models import PaymentRelease

        pr_qs = (
            PurchaseRequest.objects.filter(requester=user)
            .select_related("project")
            .order_by("-created_at")[:10]
        )
        payment_qs = (
            PaymentRelease.objects.filter(requester=user)
            .select_related("project")
            .order_by("-created_at")[:10]
        )
        delivery_qs = (
            DeliverySubmission.objects.filter(requester=user)
            .order_by("-created_at")[:10]
        )

        def _pr_item(pr):
            return {
                "id": pr.pk,
                "request_number": pr.request_number,
                "vendor": pr.vendor,
                "currency": pr.currency,
                "total_price": str(pr.total_price),
                "status": pr.status,
                "project": pr.project.name if pr.project_id else None,
                "created_at": pr.created_at.isoformat(),
            }

        def _payment_item(p):
            return {
                "id": p.pk,
                "request_number": p.request_number,
                "vendor": p.vendor,
                "currency": p.currency,
                "total_price": str(p.total_price),
                "status": p.status,
                "project": p.project.name if p.project_id else None,
                "created_at": p.created_at.isoformat(),
            }

        def _delivery_item(d):
            return {
                "id": d.pk,
                "request_number": d.request_number,
                "vendor": d.vendor,
                "currency": d.currency,
                "total_price": str(d.total_price),
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }

        data = {
            "purchase_requests": [_pr_item(pr) for pr in pr_qs],
            "payment_releases": [_payment_item(p) for p in payment_qs],
            "delivery_submissions": [_delivery_item(d) for d in delivery_qs],
        }
        return Response(data)


class PendingApprovalsView(APIView):
    """
    GET /api/v1/dashboard/pending-approvals/

    Returns items pending the current user's approval, based on their role.
    Requesters receive an empty list.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = _get_user_role(user)

        from orders.models import PurchaseRequest
        from payments.models import PaymentRelease

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

        pr_qs = pr_qs.select_related("requester", "project").order_by("-created_at")[:20]
        payment_qs = payment_qs.select_related("requester", "project").order_by("-created_at")[:20]

        def _pr_item(pr):
            return {
                "type": "PR",
                "id": pr.pk,
                "request_number": pr.request_number,
                "requester": pr.requester.get_full_name() or pr.requester.username,
                "vendor": pr.vendor,
                "currency": pr.currency,
                "total_price": str(pr.total_price),
                "status": pr.status,
                "project": pr.project.name if pr.project_id else None,
                "created_at": pr.created_at.isoformat(),
                "detail_url": f"/purchase-requests/{pr.pk}/",
            }

        def _payment_item(p):
            return {
                "type": "Payment",
                "id": p.pk,
                "request_number": p.request_number,
                "requester": p.requester.get_full_name() or p.requester.username,
                "vendor": p.vendor,
                "currency": p.currency,
                "total_price": str(p.total_price),
                "status": p.status,
                "project": p.project.name if p.project_id else None,
                "created_at": p.created_at.isoformat(),
                "detail_url": f"/payment-releases/{p.pk}/",
            }

        items = (
            [_pr_item(pr) for pr in pr_qs]
            + [_payment_item(p) for p in payment_qs]
        )
        # Sort combined list by created_at descending.
        items.sort(key=lambda x: x["created_at"], reverse=True)

        return Response({"pending_approvals": items, "total": len(items)})
