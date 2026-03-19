"""Integration tests for accounts API endpoints."""
import pytest

from django.contrib.auth.models import User


_ME_URL = "/api/v1/auth/me/"
_TOKEN_URL = "/api/v1/auth/token/"


# ---------------------------------------------------------------------------
# /api/v1/auth/me/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMeView:
    def test_authenticated_returns_user_info(self, api_client, regular_user):
        resp = api_client.get(_ME_URL)
        assert resp.status_code == 200
        data = resp.data
        assert data["username"] == regular_user.username
        assert data["id"] == regular_user.pk

    def test_response_includes_profile(self, api_client, regular_user):
        resp = api_client.get(_ME_URL)
        assert resp.status_code == 200
        assert "profile" in resp.data
        assert resp.data["profile"]["role"] == "requester"

    def test_response_includes_role_flags(self, api_client, regular_user):
        resp = api_client.get(_ME_URL)
        assert "is_pcm_approver" in resp.data
        assert "is_final_approver" in resp.data
        assert "is_admin_role" in resp.data

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.get(_ME_URL)
        assert resp.status_code == 403

    def test_pcm_approver_role_flags(self, api_client_pcm):
        resp = api_client_pcm.get(_ME_URL)
        assert resp.status_code == 200
        assert resp.data["is_pcm_approver"] is True
        assert resp.data["is_final_approver"] is False

    def test_final_approver_role_flags(self, api_client_final):
        resp = api_client_final.get(_ME_URL)
        assert resp.status_code == 200
        assert resp.data["is_final_approver"] is True
        assert resp.data["is_pcm_approver"] is False


# ---------------------------------------------------------------------------
# /api/v1/auth/token/ – Token generation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTokenView:
    def test_post_returns_token(self, api_client, regular_user):
        resp = api_client.post(_TOKEN_URL)
        assert resp.status_code == 200
        assert "token" in resp.data
        assert len(resp.data["token"]) > 10

    def test_token_response_includes_user(self, api_client, regular_user):
        resp = api_client.post(_TOKEN_URL)
        assert "user" in resp.data
        assert resp.data["user"]["username"] == regular_user.username

    def test_unauthenticated_returns_403(self, anon_client):
        resp = anon_client.post(_TOKEN_URL)
        assert resp.status_code == 403

    def test_repeated_post_returns_same_token(self, api_client, regular_user):
        resp1 = api_client.post(_TOKEN_URL)
        resp2 = api_client.post(_TOKEN_URL)
        assert resp1.data["token"] == resp2.data["token"]
