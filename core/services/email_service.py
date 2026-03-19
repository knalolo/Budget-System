"""
Email notification service.

Phase 1 stub: creates an EmailNotificationLog record and attempts delivery
via Django's built-in send_mail. Full template rendering and retry logic
will be added in Phase 3C.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from django.core.mail import send_mail
from django.template import Context, Template
from django.conf import settings

if TYPE_CHECKING:
    from django.db.models import Model

from core.models import EmailNotificationLog

logger = logging.getLogger(__name__)


def send_notification(
    subject: str,
    body_template: str,
    context: dict[str, Any],
    recipients: list[str],
    cc: list[str] | None = None,
    related_object: "Model | None" = None,
) -> EmailNotificationLog:
    """
    Send an email notification and record the attempt.

    Args:
        subject:        Email subject line.
        body_template:  Django template string for the email body.
        context:        Template context dictionary.
        recipients:     List of primary recipient email addresses.
        cc:             Optional list of CC email addresses.
        related_object: Optional model instance to link this log entry to.

    Returns:
        The persisted EmailNotificationLog instance.
    """
    cc_list: list[str] = cc or []

    rendered_body = _render_body(body_template, context)

    log = EmailNotificationLog(
        subject=subject,
        body=rendered_body,
        recipients=recipients,
        cc_recipients=cc_list,
        status="pending",
    )

    if related_object is not None:
        from django.contrib.contenttypes.models import ContentType
        log.content_type = ContentType.objects.get_for_model(related_object)
        log.object_id = related_object.pk

    log.save()

    try:
        send_mail(
            subject=subject,
            message=rendered_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        log.status = "sent"
        log.sent_at = datetime.now(tz=timezone.utc)
        logger.info(
            "Email sent: subject=%r recipients=%r", subject, recipients
        )
    except Exception as exc:  # noqa: BLE001
        log.status = "failed"
        log.error_message = str(exc)
        logger.error(
            "Email failed: subject=%r recipients=%r error=%s",
            subject,
            recipients,
            exc,
        )

    log.save(update_fields=["status", "sent_at", "error_message"])
    return log


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _render_body(body_template: str, context: dict[str, Any]) -> str:
    """Render a Django template string with the given context dict."""
    try:
        template = Template(body_template)
        return template.render(Context(context))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Template rendering failed: %s", exc)
        return body_template
