from pathlib import Path
import importlib

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import clear_url_caches


@pytest.mark.django_db
@override_settings(DEBUG=True, ROOT_URLCONF="config.urls")
def test_media_files_are_served_in_debug(client):
    import config.urls as project_urls

    clear_url_caches()
    importlib.reload(project_urls)

    media_root = Path(settings.MEDIA_ROOT)
    test_file = media_root / "test-media-serving.txt"
    test_file.write_text("media ok", encoding="utf-8")

    try:
        response = client.get(f"{settings.MEDIA_URL}test-media-serving.txt")

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"media ok"
    finally:
        response.close()
        if test_file.exists():
            test_file.unlink()
