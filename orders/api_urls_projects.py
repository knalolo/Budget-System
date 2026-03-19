"""API URL configuration for project endpoints."""

from rest_framework.routers import DefaultRouter

from .api_views import ProjectViewSet

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")

urlpatterns = router.urls
