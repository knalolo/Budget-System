"""DRF ViewSet for AssetRegistration."""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AssetRegistration
from .serializers import (
    AssetRegistrationDetailSerializer,
    AssetRegistrationListSerializer,
)
from .services import export_csv, get_csv_template, mark_imported

logger = logging.getLogger(__name__)


class AssetRegistrationViewSet(viewsets.ModelViewSet):
    """CRUD viewset for AssetRegistration with CSV export actions."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            AssetRegistration.objects.select_related(
                "requester",
                "payment_release",
                "payment_release__purchase_request",
                "purchase_request",
            )
            .prefetch_related("items")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return AssetRegistrationListSerializer
        return AssetRegistrationDetailSerializer

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="export-csv")
    def export_csv_action(self, request, pk=None):
        """Generate and download a CSV file for the given registration."""
        registration = self.get_object()
        try:
            return export_csv(registration)
        except Exception as exc:
            logger.exception("CSV export failed for registration %s: %s", pk, exc)
            return Response(
                {"error": "Failed to generate CSV export."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="template")
    def template(self, request):
        """Return an empty AssetTiger import template CSV."""
        try:
            return get_csv_template()
        except Exception as exc:
            logger.exception("Failed to generate CSV template: %s", exc)
            return Response(
                {"error": "Failed to generate CSV template."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="mark-imported")
    def mark_imported_action(self, request, pk=None):
        """Mark a registration as imported in AssetTiger."""
        registration = self.get_object()
        if registration.status != "exported":
            return Response(
                {"error": "Only exported registrations can be marked as imported."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = mark_imported(registration)
        serializer = AssetRegistrationDetailSerializer(
            updated, context={"request": request}
        )
        return Response(serializer.data)
