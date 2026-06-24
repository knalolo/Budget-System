"""
UserProfile model for the accounts app.

Extends the built-in Django User via a OneToOne relationship and adds
permission flags used throughout the procurement system.
"""
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Extended profile attached to every Django User."""

    PERMISSION_FIELDS = (
        "is_requester",
        "is_project_approver",
        "is_non_project_approver",
        "is_office_approver",
        "is_final_approver",
        "is_admin",
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    # Legacy single-role field retained temporarily for backward compatibility
    # while the rest of the application is migrated to multi-permission logic.
    role = models.CharField(
        max_length=20,
        default=settings.ROLE_REQUESTER,
        blank=True,
    )
    is_requester = models.BooleanField(default=True)
    is_project_approver = models.BooleanField(default=False)
    is_non_project_approver = models.BooleanField(default=False)
    is_office_approver = models.BooleanField(default=False)
    is_final_approver = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    display_name = models.CharField(max_length=100, blank=True)
    azure_oid = models.CharField(
        max_length=100,
        blank=True,
        unique=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.primary_role_display})"

    def clean(self) -> None:
        super().clean()
        is_active_user = bool(self.user_id and self.user.is_active)

        if self.is_admin and any(
            getattr(self, field_name)
            for field_name in self.PERMISSION_FIELDS
            if field_name != "is_admin"
        ):
            raise ValidationError(
                "Admin must be a standalone permission and cannot be combined with requester or approver permissions."
            )

        self._validate_active_admin_retention()

        if is_active_user and not self.is_admin and not self.has_any_business_permission:
            raise ValidationError(
                "Each active user profile must have at least one business permission."
            )

        if is_active_user:
            self._validate_unique_active_permission(
                "is_project_approver",
                "Only one active account can hold Project Approver permission.",
            )
            self._validate_unique_active_permission(
                "is_non_project_approver",
                "Only one active account can hold Non-Project Approver permission.",
            )
            self._validate_unique_active_permission(
                "is_office_approver",
                "Only one active account can hold Office Approver permission.",
            )
            self._validate_unique_active_permission(
                "is_final_approver",
                "Only one active account can hold Final Approver permission.",
            )
            self._validate_unique_active_permission(
                "is_admin",
                "Only one active account can hold Admin permission.",
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        self.role = self.legacy_role
        super().save(*args, **kwargs)

    def _validate_unique_active_permission(self, field_name: str, message: str) -> None:
        if not getattr(self, field_name):
            return

        conflicting_profiles = UserProfile.objects.filter(
            **{
                field_name: True,
                "user__is_active": True,
            }
        ).exclude(pk=self.pk)

        if conflicting_profiles.exists():
            raise ValidationError(message)

    def _validate_active_admin_retention(self) -> None:
        """
        Prevent the system from losing its last active standalone Admin account.

        This is only enforced when editing an existing profile that currently owns
        the active Admin permission.
        """
        if not self.pk or not self.user_id:
            return

        try:
            original = UserProfile.objects.select_related("user").get(pk=self.pk)
        except UserProfile.DoesNotExist:
            return

        current_user_is_active = User.objects.filter(pk=self.user_id).values_list(
            "is_active",
            flat=True,
        ).first()

        other_active_admin_exists = UserProfile.objects.filter(
            is_admin=True,
            user__is_active=True,
        ).exclude(pk=self.pk).exists()

        is_removing_admin_permission = bool(original.is_admin and not self.is_admin)
        is_deactivating_current_admin = bool(original.is_admin and not current_user_is_active)

        if not other_active_admin_exists and (
            is_removing_admin_permission or is_deactivating_current_admin
        ):
            raise ValidationError(
                "At least one active standalone Admin account must remain assigned."
            )

    def apply_permission_flags(self, **flags) -> None:
        """Apply a batch of permission flags before saving."""
        for field_name in self.PERMISSION_FIELDS:
            if field_name in flags:
                setattr(self, field_name, bool(flags[field_name]))

    @property
    def is_purchase_type_approver(self) -> bool:
        return self.is_project_approver or self.is_non_project_approver or self.is_office_approver

    @property
    def is_pcm_approver(self) -> bool:
        """Legacy alias for API/test compatibility; prefer is_purchase_type_approver."""
        return self.is_purchase_type_approver

    @property
    def has_any_business_permission(self) -> bool:
        return any(
            getattr(self, field_name)
            for field_name in self.PERMISSION_FIELDS
            if field_name != "is_admin"
        )

    @property
    def approver_permissions(self) -> list[str]:
        permissions: list[str] = []
        if self.is_project_approver:
            permissions.append("project")
        if self.is_non_project_approver:
            permissions.append("non_project")
        if self.is_office_approver:
            permissions.append("office")
        if self.is_final_approver:
            permissions.append("final")
        return permissions

    @property
    def permission_labels(self) -> list[str]:
        labels: list[str] = []
        if self.is_admin:
            labels.append("Admin")
            return labels
        if self.is_requester:
            labels.append("Requester")
        if self.is_project_approver:
            labels.append("Project Approver")
        if self.is_non_project_approver:
            labels.append("Non-Project Approver")
        if self.is_office_approver:
            labels.append("Office Approver")
        if self.is_final_approver:
            labels.append("Final Approver")
        return labels

    @property
    def primary_role(self) -> str:
        if self.is_admin:
            return "admin"
        if self.is_final_approver:
            return "final_approver"
        if self.is_project_approver:
            return "project_approver"
        if self.is_non_project_approver:
            return "non_project_approver"
        if self.is_office_approver:
            return "office_approver"
        return "requester"

    @property
    def primary_role_display(self) -> str:
        labels = {
            "admin": "Admin",
            "final_approver": "Final Approver",
            "project_approver": "Project Approver",
            "non_project_approver": "Non-Project Approver",
            "office_approver": "Office Approver",
            "requester": "Requester",
        }
        return labels[self.primary_role]

    @property
    def legacy_role(self) -> str:
        if self.is_admin:
            return settings.ROLE_ADMIN
        if self.is_final_approver:
            return settings.ROLE_FINAL_APPROVER
        if self.is_purchase_type_approver:
            return settings.ROLE_PURCHASE_TYPE_APPROVER
        return settings.ROLE_REQUESTER

    @property
    def can_create_requests(self) -> bool:
        return self.is_requester and not self.is_admin

    @property
    def is_approval_only(self) -> bool:
        return (
            not self.is_admin
            and not self.is_requester
            and (
                self.is_project_approver
                or self.is_non_project_approver
                or self.is_office_approver
                or self.is_final_approver
            )
        )

    @property
    def can_view_all_requests(self) -> bool:
        return self.is_admin or self.is_purchase_type_approver or self.is_final_approver

    def can_approve_purchase_type(self, purchase_type: str) -> bool:
        if purchase_type == settings.PURCHASE_TYPE_PROJECT:
            return self.is_project_approver
        if purchase_type == settings.PURCHASE_TYPE_NON_PROJECT:
            return self.is_non_project_approver
        if purchase_type == settings.PURCHASE_TYPE_OFFICE:
            return self.is_office_approver
        return False


# ---------------------------------------------------------------------------
# Signal: auto-create UserProfile when a new User is saved
# ---------------------------------------------------------------------------

@receiver(post_save, sender=User)
def create_user_profile(sender: type, instance: User, created: bool, **kwargs: object) -> None:
    """Create a UserProfile whenever a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)
