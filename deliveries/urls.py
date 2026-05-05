"""URL configuration for the deliveries app (delivery submission views)."""
from django.urls import path

from .views import (
    DeliverySubmissionDetailView,
    DeliverySubmissionListView,
    delivery_submission_create,
    delivery_submission_delete,
    delivery_submission_update,
    delivery_submission_upload,
)

app_name = "deliveries"

urlpatterns = [
    path("", DeliverySubmissionListView.as_view(), name="list"),
    path("new/", delivery_submission_create, name="create"),
    path("<int:pk>/edit/", delivery_submission_update, name="update"),
    path("<int:pk>/", DeliverySubmissionDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", delivery_submission_delete, name="delete"),
    path("<int:pk>/upload/", delivery_submission_upload, name="upload"),
]
