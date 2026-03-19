"""API URL configuration for purchase request endpoints."""

from rest_framework.routers import DefaultRouter

from .api_views import PurchaseRequestViewSet

router = DefaultRouter()
router.register(r"purchase-requests", PurchaseRequestViewSet, basename="purchase-request")

urlpatterns = router.urls
