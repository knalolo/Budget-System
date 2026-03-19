"""Unit tests for accounts app models."""
import pytest
from django.contrib.auth.models import User

from accounts.models import UserProfile


@pytest.mark.django_db
class TestUserProfileModel:
    def test_profile_auto_created_on_user_creation(self):
        """UserProfile is auto-created via post_save signal with related_name='profile'."""
        user = User.objects.create_user(username="newuser", password="pass")
        assert hasattr(user, "profile")
        assert user.profile is not None

    def test_default_role_is_requester(self):
        user = User.objects.create_user(username="defuser", password="pass")
        assert user.profile.role == "requester"

    def test_str_representation(self):
        user = User.objects.create_user(username="struser", password="pass")
        profile_str = str(user.profile)
        assert "struser" in profile_str

    def test_is_pcm_approver_property(self):
        user = User.objects.create_user(username="pcmuser", password="pass")
        user.profile.role = "pcm_approver"
        user.profile.save()
        assert user.profile.is_pcm_approver is True
        assert user.profile.is_final_approver is False
        assert user.profile.is_admin is False

    def test_is_final_approver_property(self):
        user = User.objects.create_user(username="finaluser", password="pass")
        user.profile.role = "final_approver"
        user.profile.save()
        assert user.profile.is_final_approver is True
        assert user.profile.is_pcm_approver is False
        assert user.profile.is_admin is False

    def test_is_admin_property(self):
        user = User.objects.create_user(username="adminuser", password="pass")
        user.profile.role = "admin"
        user.profile.save()
        assert user.profile.is_admin is True
        assert user.profile.is_pcm_approver is False
        assert user.profile.is_final_approver is False

    def test_requester_role_all_approver_flags_false(self):
        user = User.objects.create_user(username="requser", password="pass")
        user.profile.role = "requester"
        user.profile.save()
        assert user.profile.is_pcm_approver is False
        assert user.profile.is_final_approver is False
        assert user.profile.is_admin is False

    def test_profile_update(self):
        user = User.objects.create_user(username="upduser", password="pass")
        user.profile.display_name = "Display Name"
        user.profile.save()
        user.refresh_from_db()
        assert user.profile.display_name == "Display Name"
