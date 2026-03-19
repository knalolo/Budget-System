"""
Admin panel views for user management, system configuration, and audit logs.

All views require the requesting user to have the 'admin' role or be staff.
HTMX is used for inline role updates and config saves.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, TemplateView

from accounts.models import UserProfile
from approvals.models import ApprovalLog
from core.models import EmailNotificationLog, SystemConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class AdminRequiredMixin(LoginRequiredMixin):
    """
    Restricts access to users who have the 'admin' role or are Django staff.

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
    """Return True if the user is staff or has the admin role."""
    if user.is_staff:
        return True
    try:
        return user.profile.is_admin
    except UserProfile.DoesNotExist:
        return False


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

class UserManagementView(AdminRequiredMixin, ListView):
    """
    Lists all users with their profiles.

    GET  – renders the user table, supports ?q= search.
    POST – handled by update_user_role function view (HTMX).
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
        context["role_choices"] = settings.ROLE_CHOICES
        return context


# ---------------------------------------------------------------------------
# System Configuration
# ---------------------------------------------------------------------------

# Config keys grouped into labelled sections for the template.
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
            # For simple scalars (numbers, strings) return the str representation.
            result[key] = str(parsed) if not isinstance(parsed, (list, dict)) else raw
        except (json.JSONDecodeError, ValueError):
            result[key] = raw

    return result


class SystemConfigView(AdminRequiredMixin, TemplateView):
    """
    GET  – render config sections pre-populated with current values.
    POST – update one section's config values (HTMX or full-page form).
    """

    template_name = "admin_panel/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sections"] = CONFIG_SECTIONS
        context["config_values"] = _load_config_values()
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

                # Type-coerce before JSON-encoding.
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

        # HTMX requests get a lightweight partial response.
        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "configSaved"},
            )

        return redirect("admin-panel:admin-config")


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

_LOGS_PAGE_SIZE = 30


class AuditLogsView(AdminRequiredMixin, TemplateView):
    """
    Displays approval and email notification logs with tab switching,
    optional date-range filtering, and pagination.

    Tab is controlled by ?tab=approval_logs|email_logs (default: approval_logs).
    Date filters: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """

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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# HTMX function views
# ---------------------------------------------------------------------------

def update_user_role(request: HttpRequest, pk: int) -> HttpResponse:
    """
    HTMX POST endpoint – change the role of user <pk>.

    Only admin or staff users may call this.
    Returns a 200 with updated row HTML on success,
    or a 403 / 400 on failure.
    """
    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    target_user = get_object_or_404(
        User.objects.select_related("profile"), pk=pk
    )
    new_role = request.POST.get("role", "").strip()

    valid_roles = {key for key, _ in settings.ROLE_CHOICES}
    if new_role not in valid_roles:
        return HttpResponse(
            f"Invalid role '{new_role}'.",
            status=400,
        )

    # Prevent admins from accidentally demoting themselves.
    if target_user == request.user and new_role != settings.ROLE_ADMIN:
        messages.warning(
            request,
            "You cannot change your own role away from admin.",
        )
        return HttpResponse(status=400)

    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.role = new_role
    profile.save(update_fields=["role", "updated_at"])

    logger.info(
        "Admin %s changed role of user %s to %s",
        request.user.username,
        target_user.username,
        new_role,
    )

    # Return a lightweight confirmation fragment for HTMX to swap in.
    role_display = dict(settings.ROLE_CHOICES).get(new_role, new_role)
    response_html = (
        f'<span class="text-green-600 text-xs font-medium">'
        f"Role updated to {role_display}"
        f"</span>"
    )
    return HttpResponse(response_html, content_type="text/html")


def update_config(request: HttpRequest) -> HttpResponse:
    """
    Standalone POST endpoint for config updates.

    Delegates to SystemConfigView.post() logic – kept separate so it can
    also be reached via /admin-panel/config/update/ for pure form posts
    without the class-based view overhead.
    """
    if not request.user.is_authenticated or not _is_admin_user(request.user):
        return HttpResponseForbidden("Permission denied.")

    if request.method != "POST":
        return HttpResponse(status=405)

    view = SystemConfigView()
    view.request = request
    view.args = ()
    view.kwargs = {}
    return view.post(request)
