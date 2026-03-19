"""API URL configuration for asset registration endpoints."""

from rest_framework.routers import DefaultRouter

from .api_views import AssetRegistrationViewSet

router = DefaultRouter()
router.register(
    r"asset-registrations",
    AssetRegistrationViewSet,
    basename="asset-registration",
)

urlpatterns = router.urls
