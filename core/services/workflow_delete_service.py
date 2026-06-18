"""Helpers for deleting an entire procurement workflow safely."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q


def delete_purchase_request_workflow(purchase_request) -> dict[str, int | str]:
    """
    Delete a purchase request together with all linked workflow records.

    This is primarily used by admin flows, where deleting "the request"
    should remove the PR, linked goods receive records, linked payment
    releases, and any asset registrations derived from them.
    """

    from assets.models import AssetRegistration
    from deliveries.models import DeliverySubmission
    from payments.models import PaymentRelease

    workflow_number = purchase_request.workflow_number

    with transaction.atomic():
        payments = PaymentRelease.objects.filter(purchase_request=purchase_request)
        payment_ids = list(payments.values_list("pk", flat=True))

        deliveries = DeliverySubmission.objects.filter(purchase_request=purchase_request)
        assets = AssetRegistration.objects.filter(
            Q(purchase_request=purchase_request)
            | Q(payment_release_id__in=payment_ids)
        ).distinct()

        asset_count = assets.count()
        delivery_count = deliveries.count()
        payment_count = payments.count()

        assets.delete()
        deliveries.delete()
        payments.delete()
        purchase_request.delete()

    return {
        "workflow_number": workflow_number,
        "payments_deleted": payment_count,
        "deliveries_deleted": delivery_count,
        "assets_deleted": asset_count,
    }


def delete_payment_workflow(payment_release) -> dict[str, int | str]:
    """Delete from a payment entry, expanding to the whole workflow when linked."""
    from assets.models import AssetRegistration

    if payment_release.purchase_request_id and payment_release.purchase_request:
        return delete_purchase_request_workflow(payment_release.purchase_request)

    workflow_number = payment_release.workflow_number
    with transaction.atomic():
        assets = AssetRegistration.objects.filter(payment_release=payment_release)
        asset_count = assets.count()
        assets.delete()
        payment_release.delete()

    return {
        "workflow_number": workflow_number,
        "payments_deleted": 1,
        "deliveries_deleted": 0,
        "assets_deleted": asset_count,
    }


def delete_delivery_workflow(delivery_submission) -> dict[str, int | str]:
    """Delete from a goods receive entry, expanding to the whole workflow when linked."""
    if delivery_submission.purchase_request_id and delivery_submission.purchase_request:
        return delete_purchase_request_workflow(delivery_submission.purchase_request)

    workflow_number = delivery_submission.workflow_number
    with transaction.atomic():
        delivery_submission.delete()

    return {
        "workflow_number": workflow_number,
        "payments_deleted": 0,
        "deliveries_deleted": 1,
        "assets_deleted": 0,
    }
