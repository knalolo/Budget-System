"""Unit tests for core services (request_number_service, file_service)."""
import io
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError

from core.services.request_number_service import (
    generate_request_number,
    _extract_max_sequence,
)
from core.services.file_service import save_attachment, validate_file


# ---------------------------------------------------------------------------
# Request number generation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRequestNumberGeneration:
    def test_format_is_prefix_date_sequence(self):
        number = generate_request_number("PR", reference_date=date(2025, 3, 19))
        assert number.startswith("PR-20250319-")

    def test_first_number_has_sequence_0001(self):
        number = generate_request_number("PR", reference_date=date(2099, 1, 1))
        assert number.endswith("-0001")

    def test_sequential_numbers_increment(self):
        """Two calls on the same day produce consecutively numbered results."""
        from orders.tests.factories import PurchaseRequestFactory

        pr1 = PurchaseRequestFactory()
        pr2 = PurchaseRequestFactory()
        # Extract sequence numbers
        seq1 = int(pr1.request_number.split("-")[-1])
        seq2 = int(pr2.request_number.split("-")[-1])
        assert seq2 == seq1 + 1

    def test_prefix_is_uppercased(self):
        number = generate_request_number("pr", reference_date=date(2099, 2, 1))
        assert number.startswith("PR-")


class TestExtractMaxSequence:
    def test_empty_list_returns_zero(self):
        assert _extract_max_sequence([]) == 0

    def test_single_entry(self):
        assert _extract_max_sequence(["PR-20250101-0005"]) == 5

    def test_multiple_entries_returns_max(self):
        numbers = ["PR-20250101-0003", "PR-20250101-0007", "PR-20250101-0001"]
        assert _extract_max_sequence(numbers) == 7

    def test_malformed_entries_skipped(self):
        numbers = ["bad_format", "PR-20250101-0002"]
        assert _extract_max_sequence(numbers) == 2


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------


class TestFileValidation:
    def _make_file(self, name, size=100):
        f = MagicMock()
        f.name = name
        f.size = size
        return f

    def test_valid_pdf_passes(self):
        f = self._make_file("document.pdf")
        validate_file(f)  # should not raise

    def test_valid_image_passes(self):
        f = self._make_file("photo.jpg")
        validate_file(f)  # should not raise

    def test_invalid_extension_raises(self):
        f = self._make_file("malicious.exe")
        with pytest.raises(ValidationError, match="not allowed"):
            validate_file(f)

    def test_oversized_file_raises(self):
        from django.conf import settings

        # Size is just 1 byte over the max
        oversized = settings.MAX_FILE_SIZE_BYTES + 1
        f = self._make_file("large_file.pdf", size=oversized)
        with pytest.raises(ValidationError, match="exceeds"):
            validate_file(f)

    def test_exactly_max_size_passes(self):
        from django.conf import settings

        f = self._make_file("max_file.pdf", size=settings.MAX_FILE_SIZE_BYTES)
        validate_file(f)  # should not raise


# ---------------------------------------------------------------------------
# save_attachment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSaveAttachment:
    def test_save_creates_file_attachment(self, regular_user, sample_project):
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("test.pdf", b"PDF content", content_type="application/pdf")
        attachment = save_attachment(
            uploaded_file=uploaded,
            content_object=sample_project,
            file_type="invoice",
            uploaded_by=regular_user,
        )
        assert attachment.pk is not None
        assert attachment.original_filename == "test.pdf"
        assert attachment.uploaded_by == regular_user

    def test_save_invalid_extension_raises(self, regular_user, sample_project):
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("virus.exe", b"bad content", content_type="application/octet-stream")
        with pytest.raises(ValidationError):
            save_attachment(
                uploaded_file=uploaded,
                content_object=sample_project,
                file_type="other",
                uploaded_by=regular_user,
            )
