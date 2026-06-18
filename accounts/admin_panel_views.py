"""
Admin panel views for user management, system configuration, and audit logs.

All views require the requesting user to have admin permission or be staff.
HTMX is used for inline permission updates and config saves.
"""
from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, TemplateView

from accounts.models import UserProfile
from approvals.models import ApprovalLog
from core.models import EmailNotificationLog, SystemConfig
from orders.models import Project

logger = logging.getLogger(__name__)

USER_PERMISSION_CHOICES: list[dict[str, str]] = [
    {"field": "is_requester", "label": "Requester"},
    {"field": "is_project_approver", "label": "Project Approver"},
    {"field": "is_non_project_approver", "label": "Non-Project Approver"},
    {"field": "is_office_approver", "label": "Office Approver"},
    {"field": "is_final_approver", "label": "Final Approver"},
    {"field": "is_admin", "label": "Admin"},
]

UNIQUE_PERMISSION_FIELDS = (
    "is_project_approver",
    "is_non_project_approver",
    "is_office_approver",
    "is_final_approver",
    "is_admin",
)


def _build_unique_permission_holders() -> dict[str, dict[str, str | int]]:
    """Return the current active holder of each unique permission."""
    holders: dict[str, dict[str, str | int]] = {}
    profiles = (
        UserProfile.objects.select_related("user")
        .filter(user__is_active=True)
        .order_by("user__username")
    )
    labels = {choice["field"]: choice["label"] for choice in USER_PERMISSION_CHOICES}

    for profile in profiles:
        for field_name in UNIQUE_PERMISSION_FIELDS:
            if not getattr(profile, field_name) or field_name in holders:
                continue
            display_name = profile.display_name or profile.user.get_full_name() or profile.user.username
            holders[field_name] = {
                "user_id": profile.user_id,
                "username": profile.user.username,
                "display_name": display_name,
                "label": labels[field_name],
            }

    return holders


class AdminRequiredMixin(LoginRequiredMixin):
    """
    Restrict access to users who have admin permission or are Django staff.

    Unauthenticated users are redirected to LOGIN_URL.
    Authenticated non-admin users receive a 403 response.
    """

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not _is_admin_user(request.user):
            return HttpResponseForbidden(
                "You do not have permission to access the admin panel."
            )

        return super().dispatch(request, *args, **kwargs)


def _is_admin_user(user: User) -> bool:
    """Return True if the user is staff or has admin permission."""
    if user.is_staff:
        return True
    try:
        return user.profile.is_admin
    except UserProfile.DoesNotExist:
        return False


class UserManagementView(AdminRequiredMixin, ListView):
    """
    List all users with their profiles and permission flags.

    POST requests are handled by ``update_user_role`` for HTMX saves.
    """

    template_name = "admin_panel/users.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related("profile").order_by("username")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                username__icontains=query
            ) | qs.filter(
                email__icontains=query
            ) | qs.filter(
                first_name__icontains=query
            ) | qs.filter(
                last_name__icontains=query
            )
            qs = qs.distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["permission_choices"] = USER_PERMISSION_CHOICES
        unique_permission_holders = _build_unique_permission_holders()
        context["unique_permission_holders"] = unique_permission_holders
        context["unique_permission_holders_json"] = json.dumps(unique_permission_holders)
        return context


CONFIG_SECTIONS: list[dict] = [
    {
        "id": "po_thresholds",
        "title": "PO Thresholds",
        "description": "Minimum order value (per currency) that requires a Purchase Order.",
        "fields": [
            {
                "key": "po_threshold_eur",
                "label": "EUR Threshold",
                "input_type": "number",
                "placeholder": "e.g. 1000",
            },
            {
                "key": "po_threshold_sgd",
                "label": "SGD Threshold",
                "input_type": "number",
                "placeholder": "e.g. 1500",
            },
            {
                "key": "po_threshold_usd",
                "label": "USD Threshold",
                "input_type": "number",
                "placeholder": "e.g. 1000",
            },
        ],
    },
    {
        "id": "notification_emails",
        "title": "Notification Emails",
        "description": "Recipients who receive approval notification emails.",
        "fields": [
            {
                "key": "notification_email_limeimei",
                "label": "Li Mei Email",
                "input_type": "email",
                "placeholder": "limei@example.com",
            },
            {
                "key": "notification_email_jolly",
                "label": "Jolly Email",
                "input_type": "email",
                "placeholder": "jolly@example.com",
            },
            {
                "key": "notification_email_jess",
                "label": "Jess Email",
                "input_type": "email",
                "placeholder": "jess@example.com",
            },
        ],
    },
    {
        "id": "credit_platforms",
        "title": "Credit Platforms",
        "description": "Comma-separated list of credit card platform names used for purchases.",
        "fields": [
            {
                "key": "credit_platforms",
                "label": "Platforms",
                "input_type": "text",
                "placeholder": "e.g. Stripe, PayPal, Wise",
            },
        ],
    },
]


def _load_config_values() -> dict[str, str]:
    """
    Return a dict mapping every config key to its current display value.

    JSON-encoded values are decoded; missing keys map to an empty string.
    """
    all_keys: list[str] = [
        field["key"]
        for section in CONFIG_SECTIONS
        for field in section["fields"]
    ]
    records = SystemConfig.objects.filter(key__in=all_keys)
    stored: dict[str, str] = {r.key: r.value for r in records}

    result: dict[str, str] = {}
    for key in all_keys:
        raw = stored.get(key, "")
        if not raw:
            result[key] = ""
            continue
        try:
            parsed = json.loads(raw)
            result[key] = str(parsed) if not isinstance(parsed, (list, dict)) else raw
        except (json.JSONDecodeError, ValueError):
            result[key] = raw

    return result


class SystemConfigView(AdminRequiredMixin, TemplateView):
    """Render and update grouped system configuration fields."""

    template_name = "admin_panel/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sections"] = CONFIG_SECTIONS
        context["config_values"] = _load_config_values()
        context["projects"] = (
            Project.objects.annotate(request_count=Count("purchaserequest"))
            .order_by("mc_number")
        )
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        updated: list[str] = []
        errors: list[str] = []

        for section in CONFIG_SECTIONS:
            for field in section["fields"]:
                key = field["key"]
                if key not in request.POST:
                    continue
                raw_value = request.POST[key].strip()
                input_type = field.get("input_type", "text")

                try:
                    if input_type == "number":
                        coerced = float(raw_value) if raw_value else None
                        value_to_store = coerced
                    else:
                        value_to_store = raw_value
                except ValueError:
                    errors.append(f"Invalid value for '{field['label']}'.")
                    continue

                try:
                    SystemConfig.set_value(
                        key=key,
                        value=value_to_store,
                        description=field["label"],
                    )
                    updated.append(field["label"])
                except Exception as exc:  # pragma: no cover
                    logger.error("Failed to save config key %s: %s", key, exc)
                    errors.append(f"Could not save '{field['label']}'.")

        if errors:
            for msg in errors:
                messages.error(request, msg)
        elif updated:
            messages.success(
                request,
                f"Configuration updated: {', '.join(updated)}.",
            )

        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "configSaved"},
            )

        return redirect("admin-panel:admin-config")


_LOGS_PAGE_SIZE = 30


class AuditLogsView(AdminRequiredMixin, TemplateView):
    """Display approval and email logs with tab switching and paging."""

    template_name = "admin_panel/logs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request

        active_tab = request.GET.get("tab", "approval_logs")
        date_from = request.GET.get("date_from", "").strip()
        date_to = request.GET.get("date_to", "").strip()

        context["active_tab"] = active_tab
        context["date_from"] = date_from
        context["date_to"] = date_to

        if active_tab == "email_logs":
            context.update(self._email_log_context(request, date_from, date_to))
        else:
            context.update(self._approval_log_context(request, date_from, date_to))

        return context

    def _approval_log_context(
        self,
        request: HttpRequest,
        date_from: str,
        date_to: str,
    ) -> dict:
        qs = ApprovalLog.objects.select_related(
            "action_by", "content_type"
        ).order_by("-created_at")

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        paginator = Paginator(qs, _LOGS_PAGE_SIZE)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        return {
            "approval_logs_page": page_obj,
            "approval_logs_total": paginator.count,
        }

    def _email_log_context(
        self,
        request: HttpRequest,
        date_from: str,
        date_to: str,
    ) -> dict:
        qs = EmailNotificationLog.objects.order_by("-created_at")

        status_filter = request.GET.get("email_status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        paginator = Paginator(qs, _LOGS_PAGE_SIZE)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        return {
            "email_logs_page": page_obj,
            "email_logs_total": paginator.count,
            "email_status_filter": status_filter,
            "email_status_choices": [
                ("", "All statuses"),
                ("pending", "Pending"),
                ("sent", "Sent"),
                ("failed", "Failed"),
            ],
        }


def update_user_role(request: HttpRequest, pk: int) -> HttpResponse:
    """
    HTMX POST endpoint – change the permissions of user ``pk``.

    Admin is standalone. If it is selected, all other permissions are
    cleared automatically. A non-admin user must retain at least one
    business permission; validation is enforced at model level.
    """

    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    target_user = get_object_or_404(
        User.objects.select_related("profile"), pk=pk
    )
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    selected_permissions = {
        field["field"]: request.POST.get(field["field"]) == "on"
        for field in USER_PERMISSION_CHOICES
    }
    is_active = request.POST.get("is_active") == "on"
    requested_admin = selected_permissions["is_admin"]

    if requested_admin:
        for field in selected_permissions:
            if field != "is_admin":
                selected_permissions[field] = False

    try:
        with transaction.atomic():
            for field, value in selected_permissions.items():
                setattr(profile, field, value)
            target_user.is_active = is_active
            target_user.save(update_fields=["is_active"])
            profile.save()
    except ValidationError as exc:
        logger.warning(
            "Admin %s hit validation while updating permissions for user %s: %s",
            request.user.username,
            target_user.username,
            exc,
        )
        error_message = "; ".join(exc.messages) if getattr(exc, "messages", None) else str(exc)
        return HttpResponse(
            f'<span class="text-red-600 text-xs font-medium">{error_message}</span>',
            status=400,
            content_type="text/html",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Admin %s failed to update permissions for user %s: %s",
            request.user.username,
            target_user.username,
            exc,
        )
        return HttpResponse(
            '<span class="text-red-600 text-xs font-medium">Could not save permissions. Please try again.</span>',
            status=400,
            content_type="text/html",
        )

    logger.info(
        "Admin %s updated permissions for user %s to %s (active=%s)",
        request.user.username,
        target_user.username,
        profile.permission_labels,
        is_active,
    )

    messages.success(
        request,
        f"Permissions updated for {target_user.username}.",
    )

    if request.headers.get("HX-Request"):
        return HttpResponse(
            "",
            status=204,
            headers={"HX-Refresh": "true"},
        )

    return redirect("admin-panel:admin-users")


def update_config(request: HttpRequest) -> HttpResponse:
    """Standalone POST endpoint for config updates."""

    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    view = SystemConfigView()
    view.request = request
    view.args = ()
    view.kwargs = {}
    return view.post(request)


def save_project(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or update an MC number master-data record from the admin panel."""
    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    project = (
        get_object_or_404(Project, pk=pk)
        if pk is not None
        else Project()
    )

    mc_number = request.POST.get("mc_number", "").strip().upper()
    name = request.POST.get("name", "").strip()
    is_active = request.POST.get("is_active") == "on"

    if not mc_number or not name:
        messages.error(request, "MC Number and Project Name are required.")
        return redirect("admin-panel:admin-config")

    project.mc_number = mc_number
    project.name = name
    project.is_active = is_active

    try:
        project.save()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Admin %s failed to save MC number %s: %s",
            request.user.username,
            mc_number,
            exc,
        )
        messages.error(request, str(exc))
        return redirect("admin-panel:admin-config")

    messages.success(
        request,
        f"MC Number {project.mc_number} saved successfully.",
    )
    return redirect("admin-panel:admin-config")


def delete_project(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove or archive an MC number from the admin panel."""
    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    project = get_object_or_404(Project, pk=pk)
    request_count = project.purchaserequest_set.count()

    if request_count:
        project.is_active = False
        project.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"MC Number {project.mc_number} is already used in requests, so it was archived instead of deleted.",
        )
    else:
        project_label = project.mc_number
        project.delete()
        messages.success(request, f"MC Number {project_label} deleted.")

    return redirect("admin-panel:admin-config")
