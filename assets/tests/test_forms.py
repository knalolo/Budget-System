"""Form tests for the assets app."""

import pytest

from assets.forms import AssetRegistrationForm
from payments.tests.factories import PaymentReleaseFactory


@pytest.mark.django_db
class TestAssetRegistrationForm:
    def test_payment_release_field_only_shows_approved_releases(self):
        approved_payment = PaymentReleaseFactory(status="approved")
        PaymentReleaseFactory(status="pending_final")
        PaymentReleaseFactory(status="draft")

        form = AssetRegistrationForm()

        queryset = form.fields["payment_release"].queryset
        assert list(queryset) == [approved_payment]

    def test_payment_release_labels_include_request_number_and_vendor(self):
        approved_payment = PaymentReleaseFactory(
            status="approved",
            request_number="RP-TEST-0001",
            vendor="NUS",
        )

        form = AssetRegistrationForm()

        label = form.fields["payment_release"].label_from_instance(approved_payment)
        assert label == "RP-TEST-0001 - NUS"
