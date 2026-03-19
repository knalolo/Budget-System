"""DRF ViewSets for Project, ExpenseCategory, and PurchaseRequest."""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from approvals.services import can_user_approve
from core.permissions import IsOwnerOrApprover

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
    mark_ordered,
    mark_po_sent,
    reject_purchase_request,
    submit_purchase_request,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role constants (mirrored from settings to avoid import-time side-effects)
# ---------------------------------------------------------------------------

_APPROVER_ROLES = {"pcm_approver", "final_approver", "admin"}


def _get_role(user) -> str | None:
    try:
        return user.userprofile.role
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

        role = _get_role(user)
        if role in _APPROVER_ROLES or (user.is_staff and user.is_active):
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
        role = _get_role(request.user)
        if role not in _APPROVER_ROLES:
            return Response(
                {"detail": "You do not have an approver role."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
        role = _get_role(request.user)
        if role not in _APPROVER_ROLES:
            return Response(
                {"detail": "You do not have an approver role."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

    @action(detail=True, methods=["post"], url_path="mark-po-sent")
    def mark_po_sent(self, request, pk=None):
        """Transition an approved purchase request to 'po_sent'."""
        pr = self.get_object()
        try:
            updated = mark_po_sent(pr)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseRequestDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="mark-ordered")
    def mark_ordered(self, request, pk=None):
        """Transition an approved or po_sent purchase request to 'ordered'."""
        pr = self.get_object()
        try:
            updated = mark_ordered(pr)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PurchaseRequestDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)
