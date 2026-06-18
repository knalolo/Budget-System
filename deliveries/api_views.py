"""DRF ViewSet for DeliverySubmission."""

import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.services.workflow_delete_service import delete_delivery_workflow

from .models import DeliverySubmission
from .serializers import (
    DeliverySubmissionCreateSerializer,
    DeliverySubmissionDetailSerializer,
    DeliverySubmissionListSerializer,
)
from .services import create_delivery_submission

logger = logging.getLogger(__name__)


def _get_profile(user):
    try:
        return user.profile
    except AttributeError:
        return None


class DeliverySubmissionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for DeliverySubmissions.

    list     GET  /api/v1/delivery-submissions/
    create   POST /api/v1/delivery-submissions/
    retrieve GET  /api/v1/delivery-submissions/{id}/
    destroy  DELETE /api/v1/delivery-submissions/{id}/

    No approval actions are needed - submissions go straight to 'submitted'.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["vendor", "status"]

    def get_queryset(self):
        qs = (
            DeliverySubmission.objects.select_related("requester", "purchase_request")
            .prefetch_related("attachments")
            .all()
        )
        profile = _get_profile(self.request.user)
        if profile and (profile.can_view_all_requests or profile.is_admin):
            return qs
        return qs.filter(requester=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return DeliverySubmissionCreateSerializer
        if self.action == "retrieve":
            return DeliverySubmissionDetailSerializer
        return DeliverySubmissionListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        files = request.FILES.getlist("files")
        submission = create_delivery_submission(
            data=serializer.validated_data,
            user=request.user,
            files=files if files else None,
        )

        output = DeliverySubmissionDetailSerializer(
            submission, context={"request": request}
        )
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        profile = _get_profile(request.user)
        is_admin = bool(profile and profile.is_admin)

        if instance.requester != request.user and not is_admin:
            return Response(
                {"detail": "You do not have permission to delete this goods recieve record."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not is_admin and not instance.requester_can_delete:
            return Response(
                {
                    "detail": (
                        "This goods recieve record can no longer be deleted because the "
                        "Purchase Type Approver or Final Approver has already acted on the "
                        "linked payment flow."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if is_admin:
            delete_delivery_workflow(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return super().destroy(request, *args, **kwargs)
