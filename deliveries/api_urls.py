"""API URL configuration for delivery submission endpoints."""
from rest_framework.routers import DefaultRouter

from .api_views import DeliverySubmissionViewSet

router = DefaultRouter()
router.register(r"", DeliverySubmissionViewSet, basename="delivery-submission")

urlpatterns = router.urls
