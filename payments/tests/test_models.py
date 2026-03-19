"""Unit tests for payments app models."""
import pytest

from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestPaymentReleaseModel:
    def test_create_payment_release(self):
        pr = PaymentReleaseFactory()
        assert pr.pk is not None
        assert pr.status == "draft"

    def test_auto_request_number_generated(self):
        pr = PaymentReleaseFactory()
        assert pr.request_number
        assert pr.request_number.startswith("RP-")

    def test_request_number_sequential(self):
        pr1 = PaymentReleaseFactory()
        pr2 = PaymentReleaseFactory()
        assert pr1.request_number != pr2.request_number

    def test_request_number_not_overwritten_on_save(self):
        pr = PaymentReleaseFactory()
        original = pr.request_number
        pr.vendor = "Updated Vendor"
        pr.save()
        pr.refresh_from_db()
        assert pr.request_number == original

    def test_str_representation(self):
        pr = PaymentReleaseFactory(vendor="PayVendor")
        assert "PayVendor" in str(pr)

    def test_is_draft_property(self):
        pr = PaymentReleaseFactory(status="draft")
        assert pr.is_draft is True
        assert pr.is_pending is False

    def test_is_pending_pcm(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        assert pr.is_pending is True
        assert pr.is_draft is False

    def test_is_pending_final(self):
        pr = PaymentReleaseFactory(status="pending_final")
        assert pr.is_pending is True

    def test_is_approved(self):
        pr = PaymentReleaseFactory(status="approved")
        assert pr.is_approved is True

    def test_is_rejected(self):
        pr = PaymentReleaseFactory(status="rejected")
        assert pr.is_rejected is True

    def test_can_be_edited_and_deleted_draft(self):
        pr = PaymentReleaseFactory(status="draft")
        assert pr.can_be_edited is True
        assert pr.can_be_deleted is True

    def test_cannot_edit_or_delete_non_draft(self):
        pr = PaymentReleaseFactory(status="pending_pcm")
        assert pr.can_be_edited is False
        assert pr.can_be_deleted is False
