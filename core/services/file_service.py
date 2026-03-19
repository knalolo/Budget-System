"""
File attachment service.

Handles validation, storage, and retrieval of FileAttachment records.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.conf import settings

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.core.files.uploadedfile import UploadedFile
    from django.db.models import Model

from core.models import FileAttachment


def validate_file(uploaded_file: "UploadedFile") -> None:
    """
    Validate an uploaded file against extension allowlist and size limit.

    Raises:
        ValidationError: if the extension is not allowed or the file exceeds
                         the configured maximum size.
    """
    ext = os.path.splitext(uploaded_file.name or "")[1].lower()
    allowed: list[str] = getattr(settings, "ALLOWED_FILE_EXTENSIONS", [])

    if allowed and ext not in allowed:
        raise ValidationError(
            f"File type '{ext}' is not allowed. "
            f"Allowed types: {', '.join(allowed)}"
        )

    max_bytes: int = getattr(settings, "MAX_FILE_SIZE_BYTES", 1_073_741_824)
    file_size = _get_file_size(uploaded_file)

    if file_size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        raise ValidationError(
            f"File size {file_size:,} bytes exceeds the maximum of "
            f"{max_mb:.0f} MB ({max_bytes:,} bytes)."
        )


def save_attachment(
    uploaded_file: "UploadedFile",
    content_object: "Model",
    file_type: str,
    uploaded_by: "AbstractUser",
) -> FileAttachment:
    """
    Persist an uploaded file as a FileAttachment linked to *content_object*.

    Args:
        uploaded_file:  The file coming in from the request.
        content_object: The model instance this attachment belongs to.
        file_type:      One of the FILE_TYPE_CHOICES keys.
        uploaded_by:    The user performing the upload.

    Returns:
        The saved FileAttachment instance.
    """
    validate_file(uploaded_file)

    content_type = ContentType.objects.get_for_model(content_object)
    file_size = _get_file_size(uploaded_file)

    attachment = FileAttachment(
        content_type=content_type,
        object_id=content_object.pk,
        file=uploaded_file,
        original_filename=uploaded_file.name or "",
        file_type=file_type,
        file_size=file_size,
        uploaded_by=uploaded_by,
    )
    attachment.save()
    return attachment


def get_attachments(content_object: "Model") -> QuerySet:
    """
    Return all FileAttachment records linked to *content_object*.

    Args:
        content_object: The model instance whose attachments to fetch.

    Returns:
        A QuerySet of FileAttachment ordered by creation date (newest first).
    """
    content_type = ContentType.objects.get_for_model(content_object)
    return FileAttachment.objects.filter(
        content_type=content_type,
        object_id=content_object.pk,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_file_size(uploaded_file: "UploadedFile") -> int:
    """Return the file size in bytes, seeking if necessary."""
    if hasattr(uploaded_file, "size") and uploaded_file.size is not None:
        return int(uploaded_file.size)
    # Fall back to seek-based measurement for in-memory files
    pos = uploaded_file.tell()
    uploaded_file.seek(0, 2)  # seek to end
    size = uploaded_file.tell()
    uploaded_file.seek(pos)   # restore position
    return size
