"""Tests for accounts template views."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.urls import reverse


@pytest.mark.django_db
def test_login_view_authenticates_with_local_email_password(client):
    user = User.objects.create_user(
        username="yimeng.wang",
        email="Yimeng.Wang@wago.com",
        password="Yimeng.Wang@wago.com",
        first_name="YIMENG",
        last_name="WANG",
    )
    user.profile.display_name = "YIMENG WANG"
    user.profile.role = "requester"
    user.profile.save(update_fields=["display_name", "role"])

    response = client.post(
        reverse("accounts:login"),
        data={
            "login_method": "local",
            "identifier": "Yimeng.Wang@wago.com",
            "password": "Yimeng.Wang@wago.com",
        },
    )

    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_login_view_rejects_bad_local_password(client):
    User.objects.create_user(
        username="yimeng.wang",
        email="Yimeng.Wang@wago.com",
        password="Yimeng.Wang@wago.com",
    )

    response = client.post(
        reverse("accounts:login"),
        data={
            "login_method": "local",
            "identifier": "Yimeng.Wang@wago.com",
            "password": "wrong-password",
        },
        follow=True,
    )

    assert response.status_code == 200
    messages = [message.message for message in response.context["messages"]]
    assert any("Invalid username/email or password." in message for message in messages)


@pytest.mark.django_db
def test_login_view_hides_microsoft_button_when_sso_not_configured(client, settings):
    settings.AZURE_AD_TENANT_ID = "your-tenant-id-here"
    settings.AZURE_AD_CLIENT_ID = "your-client-id-here"
    settings.AZURE_AD_CLIENT_SECRET = "your-client-secret-here"

    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert "Sign in with Microsoft 365" not in response.content.decode()


@pytest.mark.django_db
def test_login_view_renders_when_already_authenticated(client):
    user = User.objects.create_user(
        username="admin",
        email="admin@local.test",
        password="BudgetAdmin123!",
        first_name="Admin",
    )
    client.force_login(user)

    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert "switch to another account" in response.content.decode()


@pytest.mark.django_db
def test_login_view_can_switch_from_existing_session(client):
    admin_user = User.objects.create_user(
        username="admin",
        email="admin@local.test",
        password="BudgetAdmin123!",
    )
    requester = User.objects.create_user(
        username="yimeng.wang",
        email="Yimeng.Wang@wago.com",
        password="Yimeng.Wang@wago.com",
        first_name="YIMENG",
        last_name="WANG",
    )
    client.force_login(admin_user)

    response = client.post(
        reverse("accounts:login"),
        data={
            "login_method": "local",
            "identifier": "Yimeng.Wang@wago.com",
            "password": "Yimeng.Wang@wago.com",
        },
    )

    assert response.status_code == 302
    assert response.url == "/"
    request_user = response.wsgi_request.user if hasattr(response, "wsgi_request") else AnonymousUser()
    assert request_user.is_authenticated
    assert request_user.pk == requester.pk


@pytest.mark.django_db
def test_logout_view_stays_local_when_sso_not_configured(client, settings):
    settings.AZURE_AD_TENANT_ID = "your-tenant-id-here"
    settings.AZURE_AD_CLIENT_ID = "your-client-id-here"
    settings.AZURE_AD_CLIENT_SECRET = "your-client-secret-here"

    user = User.objects.create_user(username="local.user", password="pw123456")
    client.force_login(user)

    response = client.get(reverse("accounts:logout"))

    assert response.status_code == 302
    assert response.url == "/auth/login/"
