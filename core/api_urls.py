"""API URL configuration for core attachment endpoints."""

from rest_framework.routers import DefaultRouter

from .api_views import FileAttachmentViewSet

router = DefaultRouter()
router.register(r"attachments", FileAttachmentViewSet, basename="attachment")

urlpatterns = router.urls
