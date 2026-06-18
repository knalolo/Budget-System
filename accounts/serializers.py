"""
Serializers for the accounts app.

The API now exposes multi-permission profile data instead of a single role.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.models import User
from rest_framework import serializers

from accounts.models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for the UserProfile model."""

    role = serializers.ReadOnlyField()
    permission_labels = serializers.ReadOnlyField()
    primary_role = serializers.ReadOnlyField()
    primary_role_display = serializers.ReadOnlyField()

    class Meta:
        model = UserProfile
        fields = [
            "role",
            "display_name",
            "is_requester",
            "is_project_approver",
            "is_non_project_approver",
            "is_office_approver",
            "is_final_approver",
            "is_admin",
            "permission_labels",
            "primary_role",
            "primary_role_display",
        ]

    def validate(self, attrs):
        profile = self.instance or UserProfile()
        for field_name in UserProfile.PERMISSION_FIELDS:
            if field_name in attrs:
                setattr(profile, field_name, attrs[field_name])
        if "display_name" in attrs:
            profile.display_name = attrs["display_name"]

        try:
            profile.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict or exc.messages)

        return attrs
        read_only_fields = [
            "permission_labels",
            "primary_role",
            "primary_role_display",
        ]


class UserSerializer(serializers.ModelSerializer):
    """Basic user representation including the nested profile."""

    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile"]
        read_only_fields = ["id", "username"]


class MeSerializer(serializers.ModelSerializer):
    """
    Full representation of the currently authenticated user.

    Includes permission flags so the frontend can make workflow decisions.
    """

    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    is_pcm_approver = serializers.SerializerMethodField()
    is_final_approver = serializers.SerializerMethodField()
    is_admin_role = serializers.SerializerMethodField()
    can_create_requests = serializers.SerializerMethodField()
    can_view_all_requests = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_staff",
            "is_superuser",
            "profile",
            "is_pcm_approver",
            "is_final_approver",
            "is_admin_role",
            "can_create_requests",
            "can_view_all_requests",
        ]
        read_only_fields = fields

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.username

    def get_is_pcm_approver(self, obj: User) -> bool:
        try:
            return obj.profile.is_pcm_approver
        except UserProfile.DoesNotExist:
            return False

    def get_is_final_approver(self, obj: User) -> bool:
        try:
            return obj.profile.is_final_approver
        except UserProfile.DoesNotExist:
            return False

    def get_is_admin_role(self, obj: User) -> bool:
        try:
            return obj.profile.is_admin
        except UserProfile.DoesNotExist:
            return False

    def get_can_create_requests(self, obj: User) -> bool:
        try:
            return obj.profile.can_create_requests
        except UserProfile.DoesNotExist:
            return False

    def get_can_view_all_requests(self, obj: User) -> bool:
        try:
            return obj.profile.can_view_all_requests
        except UserProfile.DoesNotExist:
            return False
