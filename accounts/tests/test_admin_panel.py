"""Integration tests for the custom admin panel."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from core.models import SystemConfig
from orders.tests.factories import ProjectFactory, PurchaseRequestFactory


@pytest.mark.django_db
class TestUpdateUserRole:
    def test_admin_can_update_username_and_display_name(self, client, admin_user, regular_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "username": "updated_requester",
                "email": "updated_requester@example.test",
                "display_name": "Updated Requester",
                "is_active": "on",
                "is_requester": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        regular_user.refresh_from_db()
        regular_user.profile.refresh_from_db()
        assert regular_user.username == "updated_requester"
        assert regular_user.profile.display_name == "Updated Requester"

    def test_admin_cannot_update_to_duplicate_username(self, client, admin_user, regular_user):
        existing_user = User.objects.create_user(
            username="existing_user",
            email="existing@example.test",
            password="pass",
        )
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "username": existing_user.username,
                "email": regular_user.email,
                "is_active": "on",
                "is_requester": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert b"Username already exists." in response.content
        regular_user.refresh_from_db()
        assert regular_user.username != existing_user.username

    def test_admin_can_update_notification_email(self, client, admin_user, regular_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "email": "requester@example.test",
                "is_active": "on",
                "is_requester": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        regular_user.refresh_from_db()
        assert regular_user.email == "requester@example.test"

    def test_admin_can_assign_requester_plus_project_approver(self, client, admin_user, regular_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "is_active": "on",
                "is_requester": "on",
                "is_project_approver": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert response.headers["HX-Refresh"] == "true"
        regular_user.refresh_from_db()
        regular_user.profile.refresh_from_db()
        assert regular_user.profile.is_requester is True
        assert regular_user.profile.is_project_approver is True
        assert regular_user.profile.is_admin is False

    def test_admin_permission_clears_other_flags(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{admin_user.pk}/update-role/",
            {
                "is_active": "on",
                "is_requester": "on",
                "is_project_approver": "on",
                "is_admin": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert response.headers["HX-Refresh"] == "true"
        admin_user.refresh_from_db()
        admin_user.profile.refresh_from_db()
        assert admin_user.profile.is_admin is True
        assert admin_user.profile.is_requester is False
        assert admin_user.profile.is_project_approver is False

    def test_admin_cannot_create_second_final_approver(self, client, admin_user, final_approver, regular_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "is_active": "on",
                "is_final_approver": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert b"Only one active account can hold Final Approver permission" in response.content
        regular_user.refresh_from_db()
        regular_user.profile.refresh_from_db()
        assert regular_user.profile.is_final_approver is False

    def test_failed_permission_change_does_not_partially_save_is_active(
        self, client, admin_user, final_approver, regular_user
    ):
        client.force_login(admin_user)
        regular_user.is_active = False
        regular_user.save(update_fields=["is_active"])

        response = client.post(
            f"/admin-panel/users/{regular_user.pk}/update-role/",
            {
                "is_active": "on",
                "is_final_approver": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        regular_user.refresh_from_db()
        assert regular_user.is_active is False

    def test_admin_cannot_remove_last_active_admin_via_admin_panel(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{admin_user.pk}/update-role/",
            {
                "is_active": "on",
                "is_requester": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert b"At least one active standalone Admin account must remain assigned" in response.content
        admin_user.refresh_from_db()
        admin_user.profile.refresh_from_db()
        assert admin_user.profile.is_admin is True

    def test_admin_cannot_deactivate_last_active_admin_via_admin_panel(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{admin_user.pk}/update-role/",
            {},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert b"At least one active standalone Admin account must remain assigned" in response.content
        admin_user.refresh_from_db()
        admin_user.profile.refresh_from_db()
        assert admin_user.is_active is True
        assert admin_user.profile.is_admin is True

    def test_user_management_page_shows_current_unique_permission_holders(self, client, admin_user, final_approver):
        client.force_login(admin_user)

        response = client.get(reverse("admin-panel:admin-users"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Current unique permission holders" in content
        assert "Final Approver" in content
        assert final_approver.username in content


@pytest.mark.django_db
class TestResetUserPassword:
    def test_admin_can_reset_user_password(self, client, admin_user, regular_user):
        regular_user.set_password("old-pass-123")
        regular_user.save(update_fields=["password"])
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-reset-password", args=[regular_user.pk]),
            {"new_password": "new-pass-456"},
        )

        assert response.status_code == 302
        regular_user.refresh_from_db()
        assert regular_user.check_password("old-pass-123") is False
        assert regular_user.check_password("new-pass-456") is True

    def test_non_admin_cannot_reset_user_password(self, client, regular_user):
        target_user = User.objects.create_user(
            username="target_user",
            email="target@example.test",
            password="old-pass-123",
        )
        client.force_login(regular_user)

        response = client.post(
            reverse("admin-panel:admin-reset-password", args=[target_user.pk]),
            {"new_password": "new-pass-456"},
        )

        assert response.status_code == 403
        target_user.refresh_from_db()
        assert target_user.check_password("old-pass-123") is True


@pytest.mark.django_db
class TestCreateUserFromAdminPanel:
    def test_admin_can_create_requester(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-user-create"),
            {
                "username": "new_requester",
                "email": "new_requester@example.com",
                "display_name": "New Requester",
                "password": "temp-pass-123",
                "is_active": "on",
                "is_requester": "on",
            },
        )

        assert response.status_code == 302
        user = User.objects.get(username="new_requester")
        assert user.email == "new_requester@example.com"
        assert user.check_password("temp-pass-123") is True
        assert user.is_active is True
        assert user.profile.display_name == "New Requester"
        assert user.profile.is_requester is True
        assert user.profile.is_admin is False

    def test_admin_permission_clears_other_flags_on_create(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-user-create"),
            {
                "username": "next_admin",
                "email": "next_admin@example.test",
                "password": "temp-pass-123",
                "is_requester": "on",
                "is_project_approver": "on",
                "is_admin": "on",
            },
        )

        assert response.status_code == 302
        user = User.objects.get(username="next_admin")
        assert user.is_active is False
        assert user.profile.is_admin is True
        assert user.profile.is_requester is False
        assert user.profile.is_project_approver is False


@pytest.mark.django_db
class TestSystemConfiguration:
    def test_notification_email_fields_save_the_keys_used_by_outbox(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-update-config"),
            {
                "notify_li_mei_email": "limei@wago.com",
                "notify_jolly_email": "jolly@wago.com",
                "notify_jess_email": "jess@wago.com",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert SystemConfig.get_value("notify_li_mei_email") == "limei@wago.com"
        assert SystemConfig.get_value("notify_jolly_email") == "jolly@wago.com"
        assert SystemConfig.get_value("notify_jess_email") == "jess@wago.com"

    def test_invalid_notification_email_is_rejected(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-update-config"),
            {"notify_jolly_email": "not-an-email"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400
        assert SystemConfig.get_value("notify_jolly_email") == "jolly@wago.com"

    def test_create_unique_permission_conflict_rolls_back_user(self, client, admin_user, final_approver):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-user-create"),
            {
                "username": "second_final",
                "password": "temp-pass-123",
                "is_active": "on",
                "is_final_approver": "on",
            },
        )

        assert response.status_code == 302
        assert not User.objects.filter(username="second_final").exists()

@pytest.mark.django_db
class TestProjectMasterDataManagement:
    def test_admin_can_create_mc_number(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-project-create"),
            {
                "mc_number": "MC009999",
                "name": "New Platform",
                "is_active": "on",
            },
        )

        assert response.status_code == 302
        project = ProjectFactory._meta.model.objects.get(mc_number="MC009999")
        assert project.name == "New Platform"
        assert project.is_active is True

    def test_admin_can_update_mc_number_name_and_status(self, client, admin_user):
        project = ProjectFactory(mc_number="MC001234", name="Legacy Name", is_active=True)
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-project-save", args=[project.pk]),
            {
                "mc_number": "MC001234",
                "name": "Updated Project Name",
            },
        )

        assert response.status_code == 302
        project.refresh_from_db()
        assert project.name == "Updated Project Name"
        assert project.is_active is False

    def test_delete_unused_mc_number_removes_record(self, client, admin_user):
        project = ProjectFactory(mc_number="MC008888")
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-project-delete", args=[project.pk]),
        )

        assert response.status_code == 302
        assert not ProjectFactory._meta.model.objects.filter(pk=project.pk).exists()

    def test_delete_used_mc_number_archives_instead_of_deleting(self, client, admin_user, regular_user):
        project = ProjectFactory(mc_number="MC007777", is_active=True)
        PurchaseRequestFactory(requester=regular_user, project=project)
        client.force_login(admin_user)

        response = client.post(
            reverse("admin-panel:admin-project-delete", args=[project.pk]),
        )

        assert response.status_code == 302
        project.refresh_from_db()
        assert project.is_active is False
