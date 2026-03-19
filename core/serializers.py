"""DRF serializers for core models (FileAttachment)."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import FileAttachment

User = get_user_model()


class UploaderSerializer(serializers.ModelSerializer):
    """Minimal user representation for the uploader field."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]
        read_only_fields = fields


class FileAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for FileAttachment – returns metadata only (no raw file bytes)."""

    file = serializers.SerializerMethodField()
    uploaded_by = UploaderSerializer(read_only=True)

    class Meta:
        model = FileAttachment
        fields = [
            "id",
            "file",
            "original_filename",
            "file_type",
            "file_size",
            "uploaded_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_file(self, obj: FileAttachment) -> str | None:
        """Return the absolute URL of the stored file, if available."""
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        if obj.file:
            return obj.file.url
        return None
