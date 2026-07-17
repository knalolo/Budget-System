"""URL configuration for the orders app (purchase request views)."""
from django.urls import path

from .views import (
    PurchaseRequestCreateView,
    PurchaseRequestDetailView,
    PurchaseRequestListView,
    PurchaseRequestUpdateView,
    purchase_request_approve,
    purchase_request_dataset_export,
    purchase_request_delete,
    purchase_request_reject,
    purchase_request_sap_reconciliation_export,
    purchase_request_submit,
    purchase_request_upload,
)

app_name = "orders"

urlpatterns = [
    path("", PurchaseRequestListView.as_view(), name="purchase-request-list"),
    path("export/dataset/", purchase_request_dataset_export, name="purchase-request-dataset-export"),
    path(
        "export/sap-reconciliation/",
        purchase_request_sap_reconciliation_export,
        name="purchase-request-sap-reconciliation-export",
    ),
    path("new/", PurchaseRequestCreateView.as_view(), name="purchase-request-create"),
    path("<int:pk>/", PurchaseRequestDetailView.as_view(), name="purchase-request-detail"),
    path("<int:pk>/edit/", PurchaseRequestUpdateView.as_view(), name="purchase-request-edit"),
    path("<int:pk>/delete/", purchase_request_delete, name="purchase-request-delete"),
    path("<int:pk>/submit/", purchase_request_submit, name="purchase-request-submit"),
    path("<int:pk>/approve/", purchase_request_approve, name="purchase-request-approve"),
    path("<int:pk>/reject/", purchase_request_reject, name="purchase-request-reject"),
    path("<int:pk>/upload/", purchase_request_upload, name="purchase-request-upload"),
]
