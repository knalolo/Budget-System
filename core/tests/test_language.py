"""Tests that browser-facing pages stay in English."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_login_page_declares_english_and_notranslate(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert response.headers["Content-Language"] == "en-us"
    assert 'lang="en"' in response.content.decode()
    assert 'content="notranslate"' in response.content.decode()


@pytest.mark.django_db
def test_admin_login_page_uses_english_branding(client):
    response = client.get("/admin/login/")
    content = response.content.decode()

    assert response.status_code == 200
    assert response.headers["Content-Language"] == "en-us"
    assert "Procurement System Administration" in content
    assert 'content="notranslate"' in content
