"""Unit tests for assets.services (CSV export and template generation)."""
import csv
import io
import pytest
from datetime import date
from decimal import Decimal

from assets.models import AssetItem, AssetRegistration
from assets.services import (
    ASSETTIGER_HEADERS,
    _build_csv_content,
    export_csv,
    get_csv_template,
    mark_imported,
)


@pytest.mark.django_db
class TestBuildCsvContent:
    def test_csv_has_header_row(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        content = _build_csv_content([])
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)
        assert headers == ASSETTIGER_HEADERS

    def test_csv_has_item_rows(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        item = AssetItem.objects.create(
            registration=reg,
            asset_name="Keyboard",
            asset_tag="AT-101",
            purchase_date=date(2025, 3, 1),
            purchase_cost=Decimal("99.50"),
        )
        content = _build_csv_content([item])
        reader = csv.reader(io.StringIO(content))
        next(reader)  # skip header
        row = next(reader)
        assert row[0] == "Keyboard"
        assert row[1] == "AT-101"
        assert row[5] == "99.50"

    def test_csv_empty_purchase_date_when_none(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        item = AssetItem.objects.create(registration=reg, asset_name="Dongle")
        content = _build_csv_content([item])
        reader = csv.reader(io.StringIO(content))
        next(reader)  # skip header
        row = next(reader)
        assert row[4] == ""  # purchase_date column


@pytest.mark.django_db
class TestExportCsv:
    def test_returns_http_response(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user, status="draft")
        response = export_csv(reg)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    def test_transitions_status_to_exported(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user, status="draft")
        export_csv(reg)
        reg.refresh_from_db()
        assert reg.status == "exported"

    def test_pending_export_also_transitions_to_exported(self, regular_user):
        reg = AssetRegistration.objects.create(
            requester=regular_user, status="pending_export"
        )
        export_csv(reg)
        reg.refresh_from_db()
        assert reg.status == "exported"

    def test_already_exported_status_unchanged(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user, status="exported")
        export_csv(reg)
        reg.refresh_from_db()
        assert reg.status == "exported"

    def test_filename_contains_registration_pk(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user)
        response = export_csv(reg)
        disposition = response["Content-Disposition"]
        assert str(reg.pk) in disposition


@pytest.mark.django_db
class TestGetCsvTemplate:
    def test_returns_http_response(self):
        response = get_csv_template()
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    def test_template_has_correct_filename(self):
        response = get_csv_template()
        assert "assettiger_import_template.csv" in response["Content-Disposition"]

    def test_template_has_only_headers(self):
        response = get_csv_template()
        content = response.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1  # just the header row
        assert rows[0] == ASSETTIGER_HEADERS


@pytest.mark.django_db
class TestMarkImported:
    def test_marks_registration_as_imported(self, regular_user):
        reg = AssetRegistration.objects.create(requester=regular_user, status="exported")
        result = mark_imported(reg)
        result.refresh_from_db()
        assert result.status == "imported"
