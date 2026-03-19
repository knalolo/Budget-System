"""
Serializers for the accounts app.

Provides read/write representations for User and UserProfile,
plus a MeSerializer that returns the full current-user payload.
"""
from django.contrib.auth.models import User
from rest_framework import serializers

from accounts.models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for the UserProfile model (nested inside UserSerializer)."""

    class Meta:
        model = UserProfile
        fields = ["role", "display_name"]
        read_only_fields = ["role"]


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

    Includes profile role details so the frontend can make
    permission decisions without a separate request.
    """

    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    is_pcm_approver = serializers.SerializerMethodField()
    is_final_approver = serializers.SerializerMethodField()
    is_admin_role = serializers.SerializerMethodField()

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
