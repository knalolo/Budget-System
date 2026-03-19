"""API URL configuration for accounts user management endpoints."""
from rest_framework.routers import DefaultRouter

from accounts.api_views import UserViewSet

router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")

urlpatterns = router.urls
