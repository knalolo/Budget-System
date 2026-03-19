"""
UserProfile model for the accounts app.

Extends the built-in Django User via a OneToOne relationship and adds
role-based access control fields used throughout the procurement system.
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Extended profile attached to every Django User."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=20,
        choices=settings.ROLE_CHOICES,
        default=settings.ROLE_REQUESTER,
    )
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
        return f"{self.user.username} ({self.get_role_display()})"

    # ------------------------------------------------------------------
    # Role convenience properties
    # ------------------------------------------------------------------

    @property
    def is_pcm_approver(self) -> bool:
        return self.role == settings.ROLE_PCM_APPROVER

    @property
    def is_final_approver(self) -> bool:
        return self.role == settings.ROLE_FINAL_APPROVER

    @property
    def is_admin(self) -> bool:
        return self.role == settings.ROLE_ADMIN


# ---------------------------------------------------------------------------
# Signal: auto-create UserProfile when a new User is saved
# ---------------------------------------------------------------------------

@receiver(post_save, sender=User)
def create_user_profile(sender: type, instance: User, created: bool, **kwargs: object) -> None:
    """Create a UserProfile whenever a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)
