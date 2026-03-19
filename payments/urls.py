"""URL configuration for the payments app (payment release template views)."""
from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    # List + create
    path("", views.PaymentReleaseListView.as_view(), name="list"),
    path("new/", views.PaymentReleaseCreateView.as_view(), name="create"),
    # Detail + edit
    path("<int:pk>/", views.PaymentReleaseDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.PaymentReleaseUpdateView.as_view(), name="update"),
    # HTMX workflow actions
    path("<int:pk>/submit/", views.submit_view, name="submit"),
    path("<int:pk>/approve/", views.approve_view, name="approve"),
    path("<int:pk>/reject/", views.reject_view, name="reject"),
    path("<int:pk>/upload/", views.upload_view, name="upload"),
    # HTMX partial for table refresh
    path("_table/", views.list_table_partial, name="list-table"),
]
