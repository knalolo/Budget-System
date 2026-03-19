"""
Shared pytest fixtures for the Budget-System test suite.

Provides factory-based fixtures for users, projects, expense categories,
and pre-authenticated DRF API clients for each role.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_factory(db):
    """Return a callable that creates unique User instances."""
    counter = {"n": 0}

    def _make(username=None, password="testpass123", role="requester", **kwargs):
        counter["n"] += 1
        uname = username or f"user{counter['n']}"
        user = User.objects.create_user(username=uname, password=password, **kwargs)
        # UserProfile is auto-created via post_save signal (related_name="profile")
        user.profile.role = role
        user.profile.save()
        return user

    return _make


@pytest.fixture
def regular_user(user_factory):
    """A plain requester-role user."""
    return user_factory(username="requester_user", role="requester")


@pytest.fixture
def pcm_approver(user_factory):
    """A PCM approver-role user."""
    return user_factory(username="pcm_approver_user", role="pcm_approver")


@pytest.fixture
def final_approver(user_factory):
    """A final approver-role user."""
    return user_factory(username="final_approver_user", role="final_approver")


@pytest.fixture
def admin_user(user_factory):
    """An admin-role user (also is_staff for Django admin access)."""
    user = user_factory(username="admin_user", role="admin")
    user.is_staff = True
    user.save()
    return user


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_project(db):
    """A single active Project instance."""
    from orders.models import Project

    return Project.objects.create(mc_number="MC-0001", name="Test Project")


@pytest.fixture
def sample_expense_category(db):
    """A single active ExpenseCategory instance."""
    from orders.models import ExpenseCategory

    return ExpenseCategory.objects.create(name="Test Category")


# ---------------------------------------------------------------------------
# API client fixtures
# ---------------------------------------------------------------------------


def _authenticated_client(user):
    """Return a DRF APIClient authenticated with a token for *user*."""
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def api_client(regular_user):
    """DRF APIClient authenticated as the regular requester user."""
    return _authenticated_client(regular_user)


@pytest.fixture
def api_client_pcm(pcm_approver):
    """DRF APIClient authenticated as the PCM approver."""
    return _authenticated_client(pcm_approver)


@pytest.fixture
def api_client_final(final_approver):
    """DRF APIClient authenticated as the final approver."""
    return _authenticated_client(final_approver)


@pytest.fixture
def api_client_admin(admin_user):
    """DRF APIClient authenticated as the admin user."""
    return _authenticated_client(admin_user)


@pytest.fixture
def anon_client():
    """Unauthenticated DRF APIClient."""
    return APIClient()
