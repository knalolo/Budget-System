"""DRF ViewSets for Project and ExpenseCategory."""

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from .models import ExpenseCategory, Project
from .serializers import ExpenseCategorySerializer, ProjectSerializer


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for Projects.

    - list / retrieve: any authenticated user
    - create / update / partial_update / destroy: admin only
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]


class ExpenseCategoryViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for ExpenseCategories.

    - list / retrieve: any authenticated user
    - create / update / partial_update / destroy: admin only
    """

    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdminUser()]
