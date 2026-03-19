"""API URL configuration for expense category endpoints."""

from rest_framework.routers import DefaultRouter

from .api_views import ExpenseCategoryViewSet

router = DefaultRouter()
router.register(r"categories", ExpenseCategoryViewSet, basename="expensecategory")

urlpatterns = router.urls
