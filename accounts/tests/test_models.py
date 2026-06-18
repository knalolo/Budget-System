"""Unit tests for accounts app models."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


@pytest.mark.django_db
class TestUserProfileModel:
    def test_profile_auto_created_on_user_creation(self):
        user = User.objects.create_user(username="newuser", password="pass")
        assert hasattr(user, "profile")
        assert user.profile is not None

    def test_default_role_is_requester(self):
        user = User.objects.create_user(username="defuser", password="pass")
        assert user.profile.role == "requester"
        assert user.profile.is_requester is True

    def test_str_representation_uses_primary_role(self):
        user = User.objects.create_user(username="struser", password="pass")
        assert "struser" in str(user.profile)
        assert "Requester" in str(user.profile)

    def test_project_approver_counts_as_pcm_approver(self):
        user = User.objects.create_user(username="pcmuser", password="pass")
        user.profile.apply_permission_flags(
            is_requester=False,
            is_project_approver=True,
        )
        user.profile.save()

        assert user.profile.is_pcm_approver is True
        assert user.profile.primary_role == "project_approver"
        assert user.profile.role == "pcm_approver"

    def test_final_approver_is_exposed_in_labels(self):
        user = User.objects.create_user(username="finaluser", password="pass")
        user.profile.apply_permission_flags(
            is_requester=False,
            is_final_approver=True,
        )
        user.profile.save()

        assert user.profile.is_final_approver is True
        assert user.profile.permission_labels == ["Final Approver"]
        assert user.profile.role == "final_approver"

    def test_admin_must_be_standalone(self):
        user = User.objects.create_user(username="adminuser", password="pass")
        user.profile.apply_permission_flags(
            is_requester=True,
            is_admin=True,
        )

        with pytest.raises(ValidationError, match="Admin must be a standalone permission"):
            user.profile.save()

    def test_only_one_active_final_approver_allowed(self):
        first = User.objects.create_user(username="final1", password="pass")
        first.profile.apply_permission_flags(
            is_requester=False,
            is_final_approver=True,
        )
        first.profile.save()

        second = User.objects.create_user(username="final2", password="pass")
        second.profile.apply_permission_flags(
            is_requester=False,
            is_final_approver=True,
        )

        with pytest.raises(ValidationError, match="Only one active account can hold Final Approver permission"):
            second.profile.save()

    def test_only_one_active_admin_allowed(self):
        first = User.objects.create_user(username="admin1", password="pass")
        first.profile.apply_permission_flags(
            is_requester=False,
            is_admin=True,
        )
        first.profile.save()

        second = User.objects.create_user(username="admin2", password="pass")
        second.profile.apply_permission_flags(
            is_requester=False,
            is_admin=True,
        )

        with pytest.raises(ValidationError, match="Only one active account can hold Admin permission"):
            second.profile.save()

    def test_last_active_admin_cannot_be_removed(self):
        user = User.objects.create_user(username="soleadmin", password="pass")
        user.profile.apply_permission_flags(
            is_requester=False,
            is_admin=True,
        )
        user.profile.save()

        user.profile.apply_permission_flags(
            is_admin=False,
            is_requester=True,
        )

        with pytest.raises(ValidationError, match="At least one active standalone Admin account must remain assigned"):
            user.profile.save()

    def test_last_active_admin_cannot_be_deactivated(self):
        user = User.objects.create_user(username="soleadmininactive", password="pass")
        user.profile.apply_permission_flags(
            is_requester=False,
            is_admin=True,
        )
        user.profile.save()

        user.is_active = False
        user.save(update_fields=["is_active"])

        with pytest.raises(ValidationError, match="At least one active standalone Admin account must remain assigned"):
            user.profile.save()

    def test_inactive_user_can_have_no_business_permission(self):
        user = User.objects.create_user(username="inactiveuser", password="pass")
        user.is_active = False
        user.save(update_fields=["is_active"])
        user.profile.apply_permission_flags(
            is_requester=False,
            is_project_approver=False,
            is_non_project_approver=False,
            is_office_approver=False,
            is_final_approver=False,
            is_admin=False,
        )

        user.profile.save()
        user.profile.refresh_from_db()
        assert user.profile.has_any_business_permission is False
