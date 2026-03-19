"""URL configuration for the assets app (asset registration views)."""

from django.urls import path

from .views import (
    AssetRegistrationCreateView,
    AssetRegistrationDetailView,
    AssetRegistrationListView,
)

app_name = "assets"

urlpatterns = [
    path("", AssetRegistrationListView.as_view(), name="list"),
    path("new/", AssetRegistrationCreateView.as_view(), name="create"),
    path("<int:pk>/", AssetRegistrationDetailView.as_view(), name="detail"),
    # POST actions (export + mark-imported) are handled by the detail view's post()
]
