"""API URL configuration for approval log endpoints."""
from rest_framework.routers import DefaultRouter

from .api_views import ApprovalLogViewSet

router = DefaultRouter()
router.register(r"", ApprovalLogViewSet, basename="approval-log")

urlpatterns = router.urls
