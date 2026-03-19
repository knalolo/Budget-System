"""API URL configuration for PaymentRelease endpoints."""
from rest_framework.routers import DefaultRouter

from .api_views import PaymentReleaseViewSet

router = DefaultRouter()
router.register(r"", PaymentReleaseViewSet, basename="payment-release")

urlpatterns = router.urls
