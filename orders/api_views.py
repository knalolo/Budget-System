"""DRF ViewSets for Project, ExpenseCategory, and PurchaseRequest."""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from approvals.services import can_user_approve
from core.permissions import IsOwnerOrApprover
from core.services.workflow_delete_service import delete_purchase_request_workflow

from .models import ExpenseCategory, Project, PurchaseRequest
from .serializers import (
    ExpenseCategorySerializer,
    ProjectSerializer,
    PurchaseRequestCreateSerializer,
    PurchaseRequestDetailSerializer,
    PurchaseRequestListSerializer,
)
from .services import (
    approve_purchase_request,
    reject_purchase_request,
    submit_purchase_request,
)

logger = logging.getLogger(__name__)


def _get_profile(user):
    """Return the attached profile or None if missing."""
    try:
        return user.profile
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# Project / ExpenseCategory viewsets
# ---------------------------------------------------------------------------


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for Projects.

    - list / retrieve: any authenticated user
    - create / update / partial_update / destroy: admin only
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]


class ExpenseCategoryViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for ExpenseCategories.

    - list / retrieve: any authenticated user
    - create / update / partial_update / destroy: admin only
    """

    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]


# ---------------------------------------------------------------------------
# PurchaseRequest viewset
# ---------------------------------------------------------------------------


class PurchaseRequestViewSet(viewsets.ModelViewSet):
    """
    Full CRUD and workflow actions for PurchaseRequests.

    Filtering:    status, project, expense_category, currency
    Search:       request_number, description, vendor
    Ordering:     -created_at (default), created_at, total_price
    """

    permission_classes = [IsAuthenticated, IsOwnerOrApprover]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "project", "expense_category", "currency"]
    search_fields = ["request_number", "description", "vendor"]
    ordering_fields = ["created_at", "total_price"]
    ordering = ["-created_at"]

    # ------------------------------------------------------------------
    # Queryset
    # ------------------------------------------------------------------

    def get_queryset(self):
        user = self.request.user
        base_qs = PurchaseRequest.objects.select_related(
            "requester",
            "expense_category",
            "project",
            "pcm_approver",
            "final_approver",
        ).prefetch_related("attachments", "approval_logs")

        profile = _get_profile(user)
        if (profile and profile.can_view_all_requests) or (
            user.is_staff and user.is_active
        ):
            return base_qs
        # Requesters see only their own requests.
        return base_qs.filter(requester=user)

    # ------------------------------------------------------------------
    # Serializer selection
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == "list":
            return PurchaseRequestListSerializer
        if self.action == "create":
            return PurchaseRequestCreateSerializer
        return PurchaseRequestDetailSerializer

    # ------------------------------------------------------------------
    # Destroy guard
    # ------------------------------------------------------------------

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        profile = _get_profile(request.user)
        if profile and profile.is_admin:
            delete_purchase_request_workflow(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        if not instance.can_be_deleted:
            return Response(
                {"detail": "Only draft purchase requests can be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Submit a draft purchase request for approval."""
        pr = self.get_object()
        try:
            updated = submit_purchase_request(pr)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseRequestDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Approve the purchase request at the current approval stage."""
        pr = self.get_object()
        can_approve, reason = can_user_approve(pr, request.user)
        if not can_approve:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        comment = request.data.get("comment", "")
        try:
            updated = approve_purchase_request(pr, request.user, comment)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseRequestDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Reject the purchase request at the current approval stage."""
        pr = self.get_object()
        can_approve, reason = can_user_approve(pr, request.user)
        if not can_approve:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        comment = request.data.get("comment", "")
        try:
            updated = reject_purchase_request(pr, request.user, comment)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseRequestDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)

