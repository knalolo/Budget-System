"""DRF ViewSet for PaymentRelease."""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.permissions import IsOwnerOrApprover
from core.services.file_service import save_attachment

from .models import PaymentRelease
from .serializers import (
    PaymentReleaseCreateSerializer,
    PaymentReleaseDetailSerializer,
    PaymentReleaseListSerializer,
)
from .services import (
    approve_payment_release,
    reject_payment_release,
    submit_payment_release,
)

logger = logging.getLogger(__name__)


class PaymentReleaseViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for PaymentRelease records.

    list     GET    /api/v1/payment-releases/
    create   POST   /api/v1/payment-releases/
    retrieve GET    /api/v1/payment-releases/{pk}/
    update   PUT    /api/v1/payment-releases/{pk}/
    partial  PATCH  /api/v1/payment-releases/{pk}/
    destroy  DELETE /api/v1/payment-releases/{pk}/
    submit   POST   /api/v1/payment-releases/{pk}/submit/
    approve  POST   /api/v1/payment-releases/{pk}/approve/
    reject   POST   /api/v1/payment-releases/{pk}/reject/
    upload   POST   /api/v1/payment-releases/{pk}/upload/
    """

    permission_classes = [IsOwnerOrApprover]
    queryset = PaymentRelease.objects.select_related(
        "requester",
        "expense_category",
        "project",
        "purchase_request",
        "pcm_approver",
        "final_approver",
    ).prefetch_related(
        "attachments",
        "approval_logs__action_by",
    ).order_by("-created_at")

    # ------------------------------------------------------------------
    # Serializer routing
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PaymentReleaseCreateSerializer
        if self.action == "retrieve":
            return PaymentReleaseDetailSerializer
        return PaymentReleaseListSerializer

    # ------------------------------------------------------------------
    # Queryset filtering
    # ------------------------------------------------------------------

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        status_filter = params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        project_filter = params.get("project", "").strip()
        if project_filter:
            try:
                qs = qs.filter(project_id=int(project_filter))
            except ValueError:
                raise DRFValidationError({"project": "Must be a valid project ID."})

        return qs

    # ------------------------------------------------------------------
    # Write path: auto-assign requester
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if not instance.can_be_edited:
            raise DRFValidationError(
                {"detail": "Only draft payment releases can be edited."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.can_be_deleted:
            raise DRFValidationError(
                {"detail": "Only draft payment releases can be deleted."}
            )
        instance.delete()

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Transition a draft PaymentRelease to pending_pcm."""
        payment = self.get_object()
        try:
            updated = submit_payment_release(payment)
        except DjangoValidationError as exc:
            raise DRFValidationError({"detail": exc.message})
        serializer = PaymentReleaseDetailSerializer(updated, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Record an approval decision at the current level."""
        payment = self.get_object()
        comment = request.data.get("comment", "")
        try:
            updated = approve_payment_release(payment, request.user, comment)
        except DjangoValidationError as exc:
            raise DRFValidationError({"detail": exc.message})
        serializer = PaymentReleaseDetailSerializer(updated, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Record a rejection decision at the current level."""
        payment = self.get_object()
        comment = request.data.get("comment", "")
        try:
            updated = reject_payment_release(payment, request.user, comment)
        except DjangoValidationError as exc:
            raise DRFValidationError({"detail": exc.message})
        serializer = PaymentReleaseDetailSerializer(updated, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="upload")
    def upload(self, request, pk=None):
        """Attach a file to this PaymentRelease."""
        payment = self.get_object()
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            raise DRFValidationError({"file": "No file provided."})

        file_type = request.data.get("file_type", "invoice")
        try:
            attachment = save_attachment(
                uploaded_file=uploaded_file,
                content_object=payment,
                file_type=file_type,
                uploaded_by=request.user,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError({"file": exc.message})

        logger.info(
            "Attachment #%s uploaded to PaymentRelease #%s by user #%s.",
            attachment.pk,
            payment.pk,
            request.user.pk,
        )
        return Response(
            {"id": attachment.pk, "filename": attachment.original_filename},
            status=status.HTTP_201_CREATED,
        )
