"""Unit tests for core app models."""
import pytest

from core.models import EmailNotificationLog, FileAttachment, SystemConfig


# ---------------------------------------------------------------------------
# SystemConfig
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSystemConfig:
    def test_set_and_get_string_value(self):
        SystemConfig.set_value("test_key", "hello")
        assert SystemConfig.get_value("test_key") == "hello"

    def test_set_and_get_numeric_value(self):
        SystemConfig.set_value("po_threshold_sgd", 1000)
        assert SystemConfig.get_value("po_threshold_sgd") == 1000

    def test_set_and_get_dict_value(self):
        SystemConfig.set_value("complex_key", {"a": 1, "b": [1, 2, 3]})
        result = SystemConfig.get_value("complex_key")
        assert result == {"a": 1, "b": [1, 2, 3]}

    def test_get_missing_key_returns_default(self):
        result = SystemConfig.get_value("nonexistent_key", default="fallback")
        assert result == "fallback"

    def test_get_missing_key_returns_none_by_default(self):
        assert SystemConfig.get_value("nonexistent_key") is None

    def test_update_existing_value(self):
        SystemConfig.set_value("update_test", 100)
        SystemConfig.set_value("update_test", 200)
        assert SystemConfig.get_value("update_test") == 200

    def test_str_representation(self):
        cfg = SystemConfig.set_value("str_key", "str_val")
        assert "str_key" in str(cfg)

    def test_set_value_returns_instance(self):
        result = SystemConfig.set_value("inst_key", 42)
        assert isinstance(result, SystemConfig)
        assert result.key == "inst_key"


# ---------------------------------------------------------------------------
# FileAttachment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFileAttachment:
    def test_create_file_attachment(self, regular_user, sample_project):
        from django.contrib.contenttypes.models import ContentType
        from orders.models import Project

        ct = ContentType.objects.get_for_model(Project)
        fa = FileAttachment.objects.create(
            content_type=ct,
            object_id=sample_project.pk,
            original_filename="invoice.pdf",
            file_type="invoice",
            file_size=12345,
            uploaded_by=regular_user,
        )
        assert fa.pk is not None
        assert fa.original_filename == "invoice.pdf"
        assert fa.file_size == 12345

    def test_str_representation(self, regular_user, sample_project):
        from django.contrib.contenttypes.models import ContentType
        from orders.models import Project

        ct = ContentType.objects.get_for_model(Project)
        fa = FileAttachment.objects.create(
            content_type=ct,
            object_id=sample_project.pk,
            original_filename="report.pdf",
            file_type="other",
            file_size=999,
            uploaded_by=regular_user,
        )
        assert "report.pdf" in str(fa)


# ---------------------------------------------------------------------------
# EmailNotificationLog
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEmailNotificationLog:
    def test_create_email_log(self):
        log = EmailNotificationLog.objects.create(
            recipients=["user@example.com"],
            cc_recipients=[],
            subject="Test Email",
            body="Test body",
            status="sent",
        )
        assert log.pk is not None
        assert log.status == "sent"

    def test_default_status_is_pending(self):
        log = EmailNotificationLog.objects.create(
            recipients=["user@example.com"],
            subject="Test",
            body="Body",
        )
        assert log.status == "pending"

    def test_str_representation(self):
        log = EmailNotificationLog.objects.create(
            recipients=["alice@example.com"],
            subject="Hello",
            body="World",
            status="sent",
        )
        result = str(log)
        assert "Hello" in result
        assert "alice@example.com" in result
