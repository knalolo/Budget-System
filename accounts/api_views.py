"""
API views for the accounts app.

Provides:
  - MeView       – GET current authenticated user info.
  - TokenView    – POST to generate / retrieve a DRF auth token (CLI auth).
  - UserViewSet  – List users and update user roles (admin only).
"""
from django.contrib.auth.models import User
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserProfile
from accounts.serializers import MeSerializer, UserProfileSerializer, UserSerializer


class MeView(APIView):
    """Return the full profile of the currently authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MeSerializer(request.user, context={"request": request})
        return Response(serializer.data)


class TokenView(APIView):
    """
    Generate or return the DRF auth token for the current user.

    Intended for CLI tooling that needs a persistent token rather than
    session-cookie authentication.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        token, created = Token.objects.get_or_create(user=request.user)
        return Response(
            {"token": token.key, "created": created},
            status=status.HTTP_200_OK,
        )


class IsAdminRolePermission(permissions.BasePermission):
    """Allow access only to users whose profile role is 'admin' or who are staff."""

    def has_permission(self, request: Request, view: object) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        try:
            return request.user.profile.is_admin
        except UserProfile.DoesNotExist:
            return False


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List and retrieve users (authenticated), update user role (admin only).

    PATCH /api/v1/users/{id}/ with {"role": "<role>"} to change a user's role.
    Only admins and staff may update roles.
    """

    queryset = User.objects.select_related("profile").order_by("username")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return UserProfileSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [IsAdminRolePermission()]
        return super().get_permissions()

    def update(self, request: Request, *args, **kwargs) -> Response:
        """Update the UserProfile fields (role) for the given user."""
        user = self.get_object()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        serializer = UserProfileSerializer(
            profile,
            data=request.data,
            partial=kwargs.pop("partial", False),
        )
        serializer.is_valid(raise_exception=True)
        # Build a new profile dict to avoid mutating the existing instance directly.
        updated_data = {**{f.name: getattr(profile, f.name) for f in profile._meta.fields}, **serializer.validated_data}
        for field, value in serializer.validated_data.items():
            setattr(profile, field, value)
        profile.save()
        return Response(UserSerializer(user, context={"request": request}).data)
