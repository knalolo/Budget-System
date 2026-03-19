"""DRF serializers for Project and ExpenseCategory."""

from rest_framework import serializers

from .models import ExpenseCategory, Project


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for the Project model."""

    class Meta:
        model = Project
        fields = ["id", "mc_number", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Serializer for the ExpenseCategory model."""

    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
