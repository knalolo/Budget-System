"""
Django admin configuration for the accounts app.

Registers UserProfile as an inline on the built-in User admin so
staff can manage role assignments without leaving the user change page.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from accounts.models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fields = (
        "display_name",
        "azure_oid",
        "role",
        "is_requester",
        "is_project_approver",
        "is_non_project_approver",
        "is_office_approver",
        "is_final_approver",
        "is_admin",
    )
    readonly_fields = ("role",)


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


# Re-register User with the extended admin class.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(UserProfile)
