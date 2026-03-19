"""
Email notification service.

Provides send_notification() as the low-level primitive and a set of
workflow-specific helpers that construct the right context and delegate to it.

Template convention
-------------------
Each logical template name resolves to two files:
  templates/emails/<name>.html  – HTML part
  templates/emails/<name>.txt   – plain-text part

SystemConfig keys used for CC recipients
-----------------------------------------
  notify_li_mei_email  – Finance (Li Mei)
  notify_jolly_email   – Procurement (Jolly), copied when a PO is required
  notify_jess_email    – Logistics (Jess), copied on DO/SO submissions
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone as dj_timezone

if TYPE_CHECKING:
    from django.db.models import Model

from core.models import EmailNotificationLog, SystemConfig

logger = logging.getLogger(__name__)

User = get_user_model()

# ---------------------------------------------------------------------------
# SystemConfig key constants
# ---------------------------------------------------------------------------

_CFG_LI_MEI_EMAIL = "notify_li_mei_email"
_CFG_JOLLY_EMAIL = "notify_jolly_email"
_CFG_JESS_EMAIL = "notify_jess_email"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_config_email(key: str) -> str:
    """Return a single email address from SystemConfig, or '' if not set."""
    value = SystemConfig.get_value(key, default="")
    return str(value).strip() if value else ""


def _build_cc(keys: list[str]) -> list[str]:
    """Return a filtered list of non-empty email addresses for the given config keys."""
    result = []
    for key in keys:
        email = _get_config_email(key)
        if email:
            result.append(email)
    return result


def _get_users_by_role(role: str) -> list[str]:
    """
    Return email addresses of all active Users whose UserProfile.role matches *role*.

    Returns an empty list when no matching users exist.
    """
    emails: list[str] = []
    try:
        users = User.objects.filter(
            is_active=True,
            profile__role=role,
        ).select_related("profile")
        for user in users:
            if user.email:
                emails.append(user.email)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to query users by role %r: %s", role, exc)
    return emails


def _requester_email(request_obj) -> list[str]:
    """Return a list containing the requester's email, or [] if not set."""
    try:
        email = request_obj.requester.email
        return [email] if email else []
    except AttributeError:
        return []


def _build_request_context(request_obj, now_str: str = "") -> dict[str, Any]:
    """
    Build a context dict common to most email templates from a request-like object.

    Handles both PurchaseRequest (has .project) and PaymentRelease (may not).
    """
    requester = getattr(request_obj, "requester", None)
    requester_name = ""
    if requester is not None:
        requester_name = (
            getattr(requester, "get_full_name", lambda: "")() or requester.username
        )

    project = getattr(request_obj, "project", None)

    ctx: dict[str, Any] = {
        "request_number": getattr(request_obj, "request_number", ""),
        "requester_name": requester_name,
        "vendor": getattr(request_obj, "vendor", ""),
        "currency": getattr(request_obj, "currency", ""),
        "amount": getattr(request_obj, "total_price", ""),
        "description": getattr(request_obj, "description", ""),
        "project": str(project) if project else "",
        "po_required": getattr(request_obj, "po_required", False),
        "detail_url": "",  # populated by callers when a URL is known
        "submitted_at": now_str or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "approved_at": now_str or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "rejected_at": now_str or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    return ctx


# ---------------------------------------------------------------------------
# Core primitive
# ---------------------------------------------------------------------------


def send_notification(
    subject: str,
    template_name: str,
    context: dict[str, Any],
    recipients: list[str],
    cc: list[str] | None = None,
    related_object: "Model | None" = None,
) -> EmailNotificationLog:
    """
    Render HTML + TXT templates, log the attempt, send via Django's mail stack,
    and update the log with the final status.

    Args:
        subject:        Email subject line.
        template_name:  Logical template name (e.g. 'emails/approval_needed').
                        Both <name>.html and <name>.txt must exist.
        context:        Template context dictionary.
        recipients:     Primary recipient email addresses.
        cc:             Optional CC email addresses.
        related_object: Optional model instance to link the log entry to.

    Returns:
        The persisted EmailNotificationLog instance.
    """
    cc_list: list[str] = [addr for addr in (cc or []) if addr]
    clean_recipients = [addr for addr in recipients if addr]

    html_body = _render_template(f"{template_name}.html", context)
    text_body = _render_template(f"{template_name}.txt", context)

    log = EmailNotificationLog(
        subject=subject,
        body=text_body,
        recipients=clean_recipients,
        cc_recipients=cc_list,
        status="pending",
        error_message="",
    )

    if related_object is not None:
        from django.contrib.contenttypes.models import ContentType
        log.content_type = ContentType.objects.get_for_model(related_object)
        log.object_id = related_object.pk

    log.save()

    if not clean_recipients:
        log.status = "failed"
        log.error_message = "No valid recipients supplied."
        log.save(update_fields=["status", "error_message"])
        logger.warning(
            "Email skipped (no recipients): subject=%r template=%r",
            subject,
            template_name,
        )
        return log

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=clean_recipients,
            cc=cc_list if cc_list else None,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)

        log.status = "sent"
        log.sent_at = dj_timezone.now()
        logger.info(
            "Email sent: subject=%r to=%r cc=%r template=%r",
            subject,
            clean_recipients,
            cc_list,
            template_name,
        )
    except Exception as exc:  # noqa: BLE001
        log.status = "failed"
        log.error_message = str(exc)
        logger.error(
            "Email failed: subject=%r to=%r error=%s",
            subject,
            clean_recipients,
            exc,
        )

    log.save(update_fields=["status", "sent_at", "error_message"])
    return log


# ---------------------------------------------------------------------------
# Workflow-specific notification functions
# ---------------------------------------------------------------------------


def notify_submission(request_obj, request_type: str) -> EmailNotificationLog | None:
    """
    Notify PCM approvers that a new request has been submitted.

    Args:
        request_obj:  PurchaseRequest or PaymentRelease instance.
        request_type: 'purchase_request' or 'payment_release'.

    Returns:
        The EmailNotificationLog entry, or None if no PCM approvers are found.
    """
    recipients = _get_users_by_role(settings.ROLE_PCM_APPROVER)
    if not recipients:
        logger.warning(
            "notify_submission: no PCM approver emails found for %s #%s",
            request_type,
            getattr(request_obj, "pk", "?"),
        )

    request_type_display = (
        "Purchase Request" if request_type == "purchase_request" else "Payment Release"
    )
    request_number = getattr(request_obj, "request_number", "")

    subject = f"[Procurement] {request_type_display} {request_number} requires your approval"
    context = _build_request_context(request_obj)
    context["request_type_display"] = request_type_display

    return send_notification(
        subject=subject,
        template_name="emails/approval_needed",
        context=context,
        recipients=recipients,
        related_object=request_obj,
    )


def notify_pcm_approved(request_obj, request_type: str) -> EmailNotificationLog | None:
    """
    Notify final approvers that a request has passed PCM review.

    Args:
        request_obj:  PurchaseRequest or PaymentRelease instance.
        request_type: 'purchase_request' or 'payment_release'.

    Returns:
        The EmailNotificationLog entry, or None if no final approvers are found.
    """
    recipients = _get_users_by_role(settings.ROLE_FINAL_APPROVER)
    if not recipients:
        logger.warning(
            "notify_pcm_approved: no final approver emails found for %s #%s",
            request_type,
            getattr(request_obj, "pk", "?"),
        )

    request_type_display = (
        "Purchase Request" if request_type == "purchase_request" else "Payment Release"
    )
    request_number = getattr(request_obj, "request_number", "")

    subject = f"[Procurement] {request_type_display} {request_number} requires your approval"
    context = _build_request_context(request_obj)
    context["request_type_display"] = request_type_display

    return send_notification(
        subject=subject,
        template_name="emails/approval_needed",
        context=context,
        recipients=recipients,
        related_object=request_obj,
    )


def notify_final_approved(request_obj, request_type: str) -> EmailNotificationLog | None:
    """
    Notify the requester (and relevant CC recipients) that a request was finally approved.

    CC rules:
    - Li Mei always included.
    - Jolly included when request_type == 'purchase_request' and po_required is True.

    Args:
        request_obj:  PurchaseRequest or PaymentRelease instance.
        request_type: 'purchase_request' or 'payment_release'.

    Returns:
        The EmailNotificationLog entry.
    """
    recipients = _requester_email(request_obj)

    cc_keys = [_CFG_LI_MEI_EMAIL]
    if request_type == "purchase_request" and getattr(request_obj, "po_required", False):
        cc_keys.append(_CFG_JOLLY_EMAIL)
    cc = _build_cc(cc_keys)

    request_number = getattr(request_obj, "request_number", "")
    context = _build_request_context(request_obj)

    if request_type == "purchase_request":
        subject = f"[Procurement] Purchase Request {request_number} has been approved"
        template_name = "emails/order_approved"
    else:
        subject = f"[Procurement] Payment Release {request_number} has been approved"
        template_name = "emails/payment_approved"

    return send_notification(
        subject=subject,
        template_name=template_name,
        context=context,
        recipients=recipients,
        cc=cc,
        related_object=request_obj,
    )


def notify_rejected(request_obj, request_type: str) -> EmailNotificationLog | None:
    """
    Notify the requester that their request was rejected.

    Args:
        request_obj:  PurchaseRequest or PaymentRelease instance.
        request_type: 'purchase_request' or 'payment_release'.

    Returns:
        The EmailNotificationLog entry.
    """
    recipients = _requester_email(request_obj)
    request_number = getattr(request_obj, "request_number", "")
    context = _build_request_context(request_obj)

    # Determine the rejection comment from the most recent rejection decision.
    rejection_comment = (
        getattr(request_obj, "final_comment", "")
        or getattr(request_obj, "pcm_comment", "")
    )
    context["rejection_comment"] = rejection_comment

    if request_type == "purchase_request":
        subject = f"[Procurement] Purchase Request {request_number} has been rejected"
        template_name = "emails/order_rejected"
    else:
        subject = f"[Procurement] Payment Release {request_number} has been rejected"
        template_name = "emails/payment_rejected"

    return send_notification(
        subject=subject,
        template_name=template_name,
        context=context,
        recipients=recipients,
        related_object=request_obj,
    )


def notify_delivery_submitted(submission) -> EmailNotificationLog | None:
    """
    Notify the requester (and CC Jess) that a DO/SO submission was completed.

    Args:
        submission: DeliverySubmission instance.

    Returns:
        The EmailNotificationLog entry.
    """
    recipients = _requester_email(submission)
    cc = _build_cc([_CFG_JESS_EMAIL])

    request_number = getattr(submission, "request_number", "")
    context = _build_request_context(submission)

    subject = f"[Procurement] DO/SO Submission {request_number}"

    return send_notification(
        subject=subject,
        template_name="emails/delivery_submitted",
        context=context,
        recipients=recipients,
        cc=cc,
        related_object=submission,
    )


# ---------------------------------------------------------------------------
# Post-approval notification dispatcher
# ---------------------------------------------------------------------------


def trigger_post_approval_notification(
    request_obj,
    action: str,
    old_status: str,
    new_status: str,
) -> EmailNotificationLog | None:
    """
    Dispatch the appropriate notification email after an approval action completes.

    Determines request type from the model class name and calls the matching
    notify_* function based on the action and new_status combination.

    Args:
        request_obj: The approvable object (PurchaseRequest or PaymentRelease).
        action:      The action string from ApprovalLog constants
                     (e.g. 'pcm_approved', 'final_approved', 'submitted').
        old_status:  Status before the action.
        new_status:  Status after the action.

    Returns:
        The EmailNotificationLog entry, or None when no email was sent.
    """
    from approvals.models import (
        ACTION_FINAL_APPROVED,
        ACTION_FINAL_REJECTED,
        ACTION_PCM_APPROVED,
        ACTION_PCM_REJECTED,
        ACTION_SUBMITTED,
    )

    model_name = type(request_obj).__name__.lower()
    if "payment" in model_name:
        request_type = "payment_release"
    else:
        request_type = "purchase_request"

    try:
        if action == ACTION_SUBMITTED:
            return notify_submission(request_obj, request_type)
        if action == ACTION_PCM_APPROVED:
            return notify_pcm_approved(request_obj, request_type)
        if action == ACTION_FINAL_APPROVED:
            return notify_final_approved(request_obj, request_type)
        if action in (ACTION_PCM_REJECTED, ACTION_FINAL_REJECTED):
            return notify_rejected(request_obj, request_type)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "trigger_post_approval_notification failed for %s #%s action=%r: %s",
            type(request_obj).__name__,
            getattr(request_obj, "pk", "?"),
            action,
            exc,
        )
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _render_template(template_path: str, context: dict[str, Any]) -> str:
    """Render a template file with the given context, returning the rendered string."""
    try:
        return render_to_string(template_path, context)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Template rendering failed for %r: %s", template_path, exc)
        return ""
