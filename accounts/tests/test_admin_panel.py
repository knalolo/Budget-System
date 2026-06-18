"""Integration tests for the custom admin panel."""

import pytest
from django.urls import reverse

from orders.tests.factories import PurchaseRequestFactory, ProjectFactory


@pytest.mark.django_db
class TestUpdateUserRole:
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

    def test_failed_permission_change_does_not_partially_save_is_active(self, client, admin_user, final_approver, regular_user):
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
