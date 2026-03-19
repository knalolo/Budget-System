"""DRF ViewSets for core models (FileAttachment)."""

import logging

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings

from .models import FileAttachment
from .serializers import FileAttachmentSerializer
from .services.file_service import save_attachment

logger = logging.getLogger(__name__)

# Maximum number of attachments allowed per object instance.
_MAX_FILES_PER_OBJECT: int = getattr(settings, "MAX_FILES_PER_REQUEST", 10)

# Valid file_type values derived from settings.
_VALID_FILE_TYPES: set[str] = {key for key, _ in getattr(settings, "FILE_TYPE_CHOICES", [])}


def _resolve_content_type(label: str) -> ContentType | None:
    """
    Resolve a dotted 'app_label.model' string to a ContentType instance.

    Returns None when the string is malformed or the model does not exist.
    """
    parts = label.split(".")
    if len(parts) != 2:
        return None
    app_label, model_name = parts
    try:
        return ContentType.objects.get(app_label=app_label, model=model_name.lower())
    except ContentType.DoesNotExist:
        return None


class FileAttachmentViewSet(viewsets.GenericViewSet):
    """
    Generic file attachment API.

    POST   /attachments/           – upload a file
    GET    /attachments/           – list attachments for a content_type+object_id
    GET    /attachments/{id}/      – retrieve metadata for one attachment
    GET    /attachments/{id}/download/ – serve the file
    DELETE /attachments/{id}/      – delete (uploader or admin only)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = FileAttachmentSerializer

    def get_queryset(self):
        return FileAttachment.objects.select_related("uploaded_by").all()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(self, request):
        """
        Return attachments filtered by content_type and object_id.

        Query params:
          content_type  – e.g. "orders.purchaserequest"
          object_id     – integer PK of the related object
        """
        content_type_label = request.query_params.get("content_type", "").strip()
        object_id_raw = request.query_params.get("object_id", "").strip()

        if not content_type_label or not object_id_raw:
            return Response(
                {"detail": "Both 'content_type' and 'object_id' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ct = _resolve_content_type(content_type_label)
        if ct is None:
            return Response(
                {"detail": f"Unknown content type: '{content_type_label}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            object_id = int(object_id_raw)
        except ValueError:
            return Response(
                {"detail": "'object_id' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = FileAttachment.objects.filter(
            content_type=ct, object_id=object_id
        ).select_related("uploaded_by")

        serializer = FileAttachmentSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def retrieve(self, request, pk=None):
        """Return metadata for a single attachment."""
        attachment = self._get_attachment_or_404(pk)
        if attachment is None:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = FileAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # Create (upload)
    # ------------------------------------------------------------------

    def create(self, request):
        """
        Upload a file and attach it to any model instance.

        Expected multipart/form-data fields:
          file          – the file to upload
          content_type  – 'app_label.model' of the target model
          object_id     – integer PK of the target instance
          file_type     – one of the FILE_TYPE_CHOICES keys
        """
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "No file provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type_label = request.data.get("content_type", "").strip()
        object_id_raw = request.data.get("object_id", "").strip()
        file_type = request.data.get("file_type", "").strip()

        # Validate required fields.
        errors: dict[str, str] = {}
        if not content_type_label:
            errors["content_type"] = "This field is required."
        if not object_id_raw:
            errors["object_id"] = "This field is required."
        if not file_type:
            errors["file_type"] = "This field is required."
        elif file_type not in _VALID_FILE_TYPES:
            errors["file_type"] = (
                f"'{file_type}' is not a valid file type. "
                f"Choose from: {', '.join(sorted(_VALID_FILE_TYPES))}."
            )
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        ct = _resolve_content_type(content_type_label)
        if ct is None:
            return Response(
                {"detail": f"Unknown content type: '{content_type_label}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            object_id = int(object_id_raw)
        except ValueError:
            return Response(
                {"detail": "'object_id' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the referenced object exists.
        model_class = ct.model_class()
        if model_class is None or not model_class.objects.filter(pk=object_id).exists():
            return Response(
                {"detail": "The referenced object does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce maximum file count per object.
        existing_count = FileAttachment.objects.filter(
            content_type=ct, object_id=object_id
        ).count()
        if existing_count >= _MAX_FILES_PER_OBJECT:
            return Response(
                {
                    "detail": (
                        f"Maximum of {_MAX_FILES_PER_OBJECT} attachments allowed per object. "
                        f"This object already has {existing_count}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_object = model_class.objects.get(pk=object_id)

        try:
            attachment = save_attachment(
                uploaded_file=uploaded_file,
                content_object=content_object,
                file_type=file_type,
                uploaded_by=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FileAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # Download action
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="download",
        parser_classes=[MultiPartParser],
    )
    def download(self, request, pk=None):
        """Serve the raw file as an attachment download."""
        attachment = self._get_attachment_or_404(pk)
        if attachment is None:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            file_handle = attachment.file.open("rb")
        except (FileNotFoundError, ValueError) as exc:
            logger.error(
                "File for attachment #%s could not be opened: %s", pk, exc
            )
            return Response(
                {"detail": "The file could not be found on the server."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=attachment.original_filename,
        )
        return response

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def destroy(self, request, pk=None):
        """Delete an attachment – only the uploader or an admin may do this."""
        attachment = self._get_attachment_or_404(pk)
        if attachment is None:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )

        is_uploader = (
            attachment.uploaded_by_id is not None
            and attachment.uploaded_by_id == request.user.pk
        )
        is_admin = getattr(request.user, "is_staff", False) or _get_role(request.user) == "admin"

        if not (is_uploader or is_admin):
            return Response(
                {"detail": "You do not have permission to delete this attachment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        attachment.file.delete(save=False)
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_attachment_or_404(self, pk) -> FileAttachment | None:
        try:
            return FileAttachment.objects.select_related("uploaded_by").get(pk=pk)
        except (FileAttachment.DoesNotExist, ValueError):
            return None


def _get_role(user) -> str | None:
    """Return the user's role string, or None if the profile is absent."""
    try:
        return user.userprofile.role
    except AttributeError:
        return None
