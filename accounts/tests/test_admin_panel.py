"""Integration tests for the custom admin panel."""

import pytest


@pytest.mark.django_db
class TestUpdateUserRole:
    def test_admin_can_change_own_role(self, client, admin_user):
        client.force_login(admin_user)

        response = client.post(
            f"/admin-panel/users/{admin_user.pk}/update-role/",
            {"role": "requester"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200

        admin_user.refresh_from_db()
        admin_user.profile.refresh_from_db()
        assert admin_user.profile.role == "requester"
