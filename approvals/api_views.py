"""
API views for the approvals app.

ApprovalLogViewSet
    Read-only viewset that returns ApprovalLog entries.
    Supports filtering by content_type label and object_id.

    GET /api/v1/approval-logs/
    GET /api/v1/approval-logs/?content_type=orders.purchaserequest&object_id=5
    GET /api/v1/approval-logs/{pk}/
"""
import logging

from django.contrib.contenttypes.models import ContentType
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError

from .models import ApprovalLog
from .serializers import ApprovalLogSerializer

logger = logging.getLogger(__name__)


class ApprovalLogViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only viewset for ApprovalLog records.

    Query parameters
    ----------------
    content_type : str
        Dotted ``app_label.model`` string, e.g. ``orders.purchaserequest``.
        Case-insensitive.
    object_id : int
        Primary key of the related object.
    """

    serializer_class = ApprovalLogSerializer
    # Default ordering: newest first (matches model Meta)
    queryset = ApprovalLog.objects.select_related(
        "content_type",
        "action_by",
    ).order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()

        content_type_label = self.request.query_params.get("content_type", "").strip()
        object_id_raw = self.request.query_params.get("object_id", "").strip()

        if content_type_label:
            qs = self._filter_by_content_type(qs, content_type_label)

        if object_id_raw:
            qs = self._filter_by_object_id(qs, object_id_raw)

        return qs

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_content_type(qs, label: str):
        """Filter queryset by dotted app_label.model string."""
        parts = label.lower().split(".")
        if len(parts) != 2:
            raise ValidationError(
                {
                    "content_type": (
                        "Provide a dotted 'app_label.model' string, "
                        "e.g. 'orders.purchaserequest'."
                    )
                }
            )
        app_label, model_name = parts
        try:
            content_type = ContentType.objects.get(
                app_label=app_label,
                model=model_name,
            )
        except ContentType.DoesNotExist:
            raise ValidationError(
                {"content_type": f"No content type found for '{label}'."}
            )
        return qs.filter(content_type=content_type)

    @staticmethod
    def _filter_by_object_id(qs, raw_value: str):
        """Filter queryset by object_id, raising 400 for non-integer values."""
        try:
            object_id = int(raw_value)
        except ValueError:
            raise ValidationError(
                {"object_id": f"'{raw_value}' is not a valid integer."}
            )
        if object_id < 1:
            raise ValidationError(
                {"object_id": "object_id must be a positive integer."}
            )
        return qs.filter(object_id=object_id)
