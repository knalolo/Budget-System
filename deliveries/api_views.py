"""DRF ViewSet for DeliverySubmission."""

import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DeliverySubmission
from .serializers import (
    DeliverySubmissionCreateSerializer,
    DeliverySubmissionDetailSerializer,
    DeliverySubmissionListSerializer,
)
from .services import create_delivery_submission

logger = logging.getLogger(__name__)


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
        return (
            DeliverySubmission.objects.select_related("requester", "purchase_request")
            .prefetch_related("attachments")
            .all()
        )

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
