"""URL configuration for the orders app (purchase request views)."""
from django.urls import path

from .views import (
    PurchaseRequestCreateView,
    PurchaseRequestDetailView,
    PurchaseRequestListView,
    PurchaseRequestUpdateView,
    purchase_request_approve,
    purchase_request_mark_ordered,
    purchase_request_mark_po_sent,
    purchase_request_reject,
    purchase_request_submit,
    purchase_request_upload,
)

app_name = "orders"

urlpatterns = [
    path("", PurchaseRequestListView.as_view(), name="purchase-request-list"),
    path("new/", PurchaseRequestCreateView.as_view(), name="purchase-request-create"),
    path("<int:pk>/", PurchaseRequestDetailView.as_view(), name="purchase-request-detail"),
    path("<int:pk>/edit/", PurchaseRequestUpdateView.as_view(), name="purchase-request-edit"),
    path("<int:pk>/submit/", purchase_request_submit, name="purchase-request-submit"),
    path("<int:pk>/approve/", purchase_request_approve, name="purchase-request-approve"),
    path("<int:pk>/reject/", purchase_request_reject, name="purchase-request-reject"),
    path("<int:pk>/upload/", purchase_request_upload, name="purchase-request-upload"),
    path("<int:pk>/mark-po-sent/", purchase_request_mark_po_sent, name="purchase-request-mark-po-sent"),
    path("<int:pk>/mark-ordered/", purchase_request_mark_ordered, name="purchase-request-mark-ordered"),
]
