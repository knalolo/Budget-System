"""
API views for SystemConfig and EmailNotificationLog.

Endpoints:
  GET  /api/v1/config/        – list all SystemConfig entries
  PATCH /api/v1/config/       – bulk-update config values (admin only)
  GET  /api/v1/email-logs/    – list EmailNotificationLog entries (admin only)
"""
from __future__ import annotations

import json
import logging

from django.http import HttpRequest
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api_views import IsAdminRolePermission
from core.models import EmailNotificationLog, SystemConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class SystemConfigSerializer(serializers.ModelSerializer):
    """Serializer for SystemConfig – exposes the decoded value."""

    decoded_value = serializers.SerializerMethodField()

    class Meta:
        model = SystemConfig
        fields = ["key", "value", "decoded_value", "description"]
        read_only_fields = ["key", "decoded_value"]

    def get_decoded_value(self, obj: SystemConfig):
        try:
            return json.loads(obj.value)
        except (json.JSONDecodeError, ValueError):
            return obj.value


class EmailNotificationLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for EmailNotificationLog."""

    class Meta:
        model = EmailNotificationLog
        fields = [
            "id",
            "subject",
            "recipients",
            "cc_recipients",
            "status",
            "error_message",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class SystemConfigListView(APIView):
    """
    GET  – return all SystemConfig entries.
    PATCH – bulk-update; body must be {"key": value, ...}.

    Admin or staff access only for PATCH; all authenticated users can GET.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest) -> Response:
        configs = SystemConfig.objects.all()
        serializer = SystemConfigSerializer(configs, many=True)
        return Response({"results": serializer.data})

    def patch(self, request: HttpRequest) -> Response:
        # Require admin for writes.
        perm = IsAdminRolePermission()
        if not perm.has_permission(request, self):
            return Response(
                {"detail": "Admin role required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        updates = request.data
        if not isinstance(updates, dict):
            return Response(
                {"detail": "Request body must be a JSON object of {key: value} pairs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        saved: list[str] = []
        errors: dict[str, str] = {}

        for key, value in updates.items():
            if not isinstance(key, str) or not key.strip():
                errors[str(key)] = "Key must be a non-empty string."
                continue
            try:
                SystemConfig.set_value(key=key.strip(), value=value)
                saved.append(key)
            except Exception as exc:
                logger.error("Config PATCH failed for key %s: %s", key, exc)
                errors[key] = "Failed to save."

        if errors:
            return Response(
                {"saved": saved, "errors": errors},
                status=status.HTTP_207_MULTI_STATUS,
            )

        return Response({"saved": saved}, status=status.HTTP_200_OK)


class EmailLogListView(APIView):
    """
    GET /api/v1/email-logs/ – list EmailNotificationLog entries.

    Admin or staff access only.

    Query params:
      status      – filter by status (pending / sent / failed)
      date_from   – ISO date YYYY-MM-DD
      date_to     – ISO date YYYY-MM-DD
      page        – page number (default 1)
      page_size   – records per page (default 20, max 100)
    """

    permission_classes = [IsAdminRolePermission]

    def get(self, request: HttpRequest) -> Response:
        qs = EmailNotificationLog.objects.order_by("-created_at")

        # Filtering
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        date_from = request.query_params.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # Pagination
        try:
            page_size = min(int(request.query_params.get("page_size", 20)), 100)
        except (ValueError, TypeError):
            page_size = 20

        try:
            page_number = max(int(request.query_params.get("page", 1)), 1)
        except (ValueError, TypeError):
            page_number = 1

        total = qs.count()
        offset = (page_number - 1) * page_size
        page_qs = qs[offset: offset + page_size]

        serializer = EmailNotificationLogSerializer(page_qs, many=True)
        return Response(
            {
                "count": total,
                "page": page_number,
                "page_size": page_size,
                "results": serializer.data,
            }
        )
