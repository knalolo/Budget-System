"""Queue procurement workflow notifications for the local Outlook worker."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.template.loader import render_to_string

from core.models import EmailOutbox, SystemConfig

logger = logging.getLogger(__name__)
User = get_user_model()

CFG_LI_MEI_EMAIL = "notify_li_mei_email"
CFG_JOLLY_EMAIL = "notify_jolly_email"
CFG_JESS_EMAIL = "notify_jess_email"


def queue_approval_event(request_obj, action: str, event_key: str) -> EmailOutbox | None:
    """Route an approval event to the matching PR or Payment queue helper."""
    from approvals.models import (
        ACTION_FINAL_APPROVED,
        ACTION_FINAL_REJECTED,
        ACTION_FIRST_STAGE_APPROVED,
        ACTION_FIRST_STAGE_REJECTED,
        ACTION_SUBMITTED,
    )

    is_payment = type(request_obj).__name__ == "PaymentRelease"
    if is_payment:
        handlers = {
            ACTION_SUBMITTED: queue_payment_submitted_email,
            ACTION_FIRST_STAGE_APPROVED: queue_payment_first_approved_email,
            ACTION_FIRST_STAGE_REJECTED: queue_payment_rejected_email,
            ACTION_FINAL_REJECTED: queue_payment_rejected_email,
            ACTION_FINAL_APPROVED: queue_payment_final_approved_email,
        }
    else:
        handlers = {
            ACTION_SUBMITTED: queue_pr_submitted_email,
            ACTION_FIRST_STAGE_APPROVED: queue_pr_first_approved_email,
            ACTION_FIRST_STAGE_REJECTED: queue_pr_rejected_email,
            ACTION_FINAL_REJECTED: queue_pr_rejected_email,
            ACTION_FINAL_APPROVED: queue_pr_final_approved_email,
        }

    handler = handlers.get(action)
    if handler is None:
        return None

    queued = handler(request_obj, event_key=event_key)
    if action == ACTION_FINAL_APPROVED:
        if is_payment:
            queue_advance_goods_followup_email(request_obj, event_key=event_key)
            if request_obj.purchase_request_id:
                queue_workflow_completed_email(request_obj.purchase_request)
        else:
            queue_workflow_completed_email(request_obj)
    return queued


def queue_pr_submitted_email(pr, *, event_key: str) -> EmailOutbox | None:
    return _queue(
        event_type="pr_submitted",
        event_key=event_key,
        recipients=_first_approver_emails(pr),
        subject=f"[Procurement] PR {pr.request_number} requires approval",
        greeting=pr.first_approver_role_label,
        message="A new Purchase Request is waiting for your approval.",
        fields=_pr_fields(pr),
        next_step="Please review the Purchase Request and approve or reject it.",
    )


def queue_pr_first_approved_email(pr, *, event_key: str) -> EmailOutbox | None:
    return _queue(
        event_type="pr_first_approved",
        event_key=event_key,
        recipients=_final_approver_emails(),
        subject=f"[Procurement] PR {pr.request_number} requires final approval",
        greeting="Final Approver",
        message="The Purchase Request passed first-stage approval and is waiting for final approval.",
        fields=_pr_fields(pr),
        next_step="Please complete the final approval review.",
    )


def queue_pr_rejected_email(pr, *, event_key: str) -> EmailOutbox | None:
    final_rejection = pr.final_decision == "rejected"
    approver = pr.final_approver if final_rejection else pr.pcm_approver
    reason = pr.final_comment if final_rejection else pr.pcm_comment
    stage = "Final Approver" if final_rejection else pr.first_approver_role_label
    return _queue(
        event_type="pr_final_rejected" if final_rejection else "pr_first_rejected",
        event_key=event_key,
        recipients=_requester_email(pr),
        subject=f"[Procurement] PR {pr.request_number} was rejected",
        greeting=_person_name(pr.requester),
        message=f"The Purchase Request was rejected by {stage}.",
        fields=_pr_fields(pr) + _rejection_fields(approver, reason),
        next_step="Please update the request and resubmit it, or close the request.",
        tone="rejected",
    )


def queue_pr_final_approved_email(pr, *, event_key: str) -> EmailOutbox | None:
    po_required = bool(pr.requires_po or pr.po_required)
    cc = [_config_email(CFG_LI_MEI_EMAIL)]
    if po_required:
        cc.append(_config_email(CFG_JOLLY_EMAIL))

    message = "The Purchase Request has completed all approval stages."
    note = ""
    if po_required:
        note = "PO Required: Yes. Jolly, please help to raise the Purchase Order for this request."

    return _queue(
        event_type="pr_final_approved",
        event_key=event_key,
        recipients=_requester_email(pr),
        cc=cc,
        subject=f"[Procurement] PR {pr.request_number} fully approved",
        greeting=_person_name(pr.requester),
        message=message,
        fields=_pr_fields(pr) + [("PO Required", "Yes" if po_required else "No")],
        next_step="You can continue with Goods Receive or Payment Release according to the purchase flow.",
        note=note,
        attachments=_attachment_paths(pr, {"quotation"}),
        required_attachment_label="Quotation",
        tone="approved",
    )


def queue_payment_submitted_email(payment, *, event_key: str) -> EmailOutbox | None:
    return _queue(
        event_type="payment_submitted",
        event_key=event_key,
        recipients=_first_approver_emails(payment),
        subject=f"[Procurement] Payment {payment.request_number} requires approval",
        greeting=payment.first_approver_role_label,
        message="A new Payment Release is waiting for your approval.",
        fields=_payment_fields(payment),
        next_step="Please review the Payment Release and approve or reject it.",
    )


def queue_payment_first_approved_email(payment, *, event_key: str) -> EmailOutbox | None:
    return _queue(
        event_type="payment_first_approved",
        event_key=event_key,
        recipients=_final_approver_emails(),
        subject=f"[Procurement] Payment {payment.request_number} requires final approval",
        greeting="Final Approver",
        message="The Payment Release passed first-stage approval and is waiting for final approval.",
        fields=_payment_fields(payment),
        next_step="Please complete the final payment approval review.",
    )


def queue_payment_rejected_email(payment, *, event_key: str) -> EmailOutbox | None:
    final_rejection = payment.final_decision == "rejected"
    approver = payment.final_approver if final_rejection else payment.pcm_approver
    reason = payment.final_comment if final_rejection else payment.pcm_comment
    stage = "Final Approver" if final_rejection else payment.first_approver_role_label
    return _queue(
        event_type="payment_final_rejected" if final_rejection else "payment_first_rejected",
        event_key=event_key,
        recipients=_requester_email(payment),
        subject=f"[Procurement] Payment {payment.request_number} was rejected",
        greeting=_person_name(payment.requester),
        message=f"The Payment Release was rejected by {stage}.",
        fields=_payment_fields(payment) + _rejection_fields(approver, reason),
        next_step="Please update the Payment Release and resubmit it.",
        tone="rejected",
    )


def queue_payment_final_approved_email(payment, *, event_key: str) -> EmailOutbox | None:
    return _queue(
        event_type="payment_final_approved",
        event_key=event_key,
        recipients=[_config_email(CFG_LI_MEI_EMAIL)],
        cc=_requester_email(payment),
        subject=f"[Procurement] Payment {payment.request_number} approved for processing",
        greeting="Li Mei",
        message="The Payment Release has completed all approval stages.",
        fields=_payment_fields(payment),
        next_step="Li Mei, please process this approved payment.",
        attachments=_attachment_paths(payment, {"invoice", "proforma_invoice"}),
        required_attachment_label="Invoice",
        tone="approved",
    )


def queue_advance_goods_followup_email(payment, *, event_key: str) -> EmailOutbox | None:
    if not payment.do_follow_up_required:
        return None
    return _queue(
        event_type="advance_payment_goods_followup",
        event_key=event_key,
        recipients=_requester_email(payment),
        subject=f"[Procurement] Goods Receive follow-up for PR {_pr_number(payment)}",
        greeting=_person_name(payment.requester),
        message="The advance payment was approved, but Goods Receive is not complete.",
        fields=_payment_fields(payment),
        next_step="Please submit or continue updating Goods Receive when the goods arrive.",
    )


def queue_goods_followup_email(delivery, *, event_key: str | None = None) -> EmailOutbox | None:
    pr = delivery.purchase_request
    if pr is None:
        return None

    if pr.goods_stage == "partially_delivered":
        message = "The goods have not been fully received."
        next_step = "Please continue updating the same Goods Receive record when more goods arrive."
    elif not pr.workflow_completed and pr.remaining_payment_required_total > 0:
        message = "Goods Receive is complete, but payment is not complete."
        next_step = "Please submit the required Payment Release."
    else:
        message = "Goods Receive has been completed."
        next_step = "No further Goods Receive update is required."

    key = event_key or f"delivery:{delivery.pk}:{delivery.updated_at.isoformat()}"
    queued = _queue(
        event_type="goods_receive_updated",
        event_key=key,
        recipients=_requester_email(delivery),
        cc=[_config_email(CFG_JESS_EMAIL)],
        subject=f"[Procurement] Goods Receive update for PR {pr.request_number}",
        greeting=_person_name(delivery.requester),
        message=message,
        fields=_goods_fields(delivery),
        next_step=next_step,
    )
    queue_workflow_completed_email(pr)
    return queued


def queue_workflow_completed_email(pr) -> EmailOutbox | None:
    if not pr.workflow_completed:
        return None
    return _queue(
        event_type="workflow_completed",
        event_key=f"pr:{pr.pk}:workflow_completed",
        recipients=_requester_email(pr),
        subject=f"[Procurement] Request {pr.request_number} completed",
        greeting=_person_name(pr.requester),
        message="The complete procurement workflow is finished.",
        fields=_pr_fields(pr) + [
            ("PR Approval", "Approved"),
            ("Goods Receive", pr.goods_stage_display),
            ("Payment", pr.payment_stage_display),
        ],
        next_step="No further action is required for this request.",
        tone="approved",
    )


def _queue(
    *,
    event_type: str,
    event_key: str,
    recipients: Iterable[str],
    subject: str,
    greeting: str,
    message: str,
    fields: list[tuple[str, object]],
    next_step: str,
    cc: Iterable[str] = (),
    note: str = "",
    attachments: list[str] | None = None,
    required_attachment_label: str = "",
    tone: str = "info",
) -> EmailOutbox | None:
    if not getattr(settings, "OUTLOOK_EMAIL_ENABLED", False):
        logger.info("Outlook email disabled; skipped event %s (%s).", event_type, event_key)
        return None

    to_emails = _valid_emails(recipients)
    cc_emails = [email for email in _valid_emails(cc) if email not in to_emails]
    body_html = render_to_string(
        "emails/workflow_notification.html",
        {
            "greeting": greeting,
            "message": message,
            "fields": fields,
            "next_step": next_step,
            "note": note,
            "tone": tone,
        },
    )
    failures: list[str] = []
    if not to_emails:
        failures.append("No valid primary recipient email is configured.")
    if required_attachment_label and not attachments:
        failures.append(f"Required {required_attachment_label} attachment is not available.")

    item, _ = EmailOutbox.objects.get_or_create(
        event_type=event_type,
        event_key=event_key,
        defaults={
            "from_mailbox": settings.OUTLOOK_FROM_MAILBOX,
            "to_emails": ";".join(to_emails),
            "cc_emails": ";".join(cc_emails),
            "subject": subject,
            "body_html": body_html,
            "attachment_paths": attachments or [],
            "status": EmailOutbox.STATUS_FAILED if failures else EmailOutbox.STATUS_PENDING,
            "last_error": " ".join(failures),
        },
    )
    if failures:
        logger.error("Outlook email event %s could not be queued: %s", event_type, " ".join(failures))
    return item


def _valid_emails(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        email = str(raw or "").strip()
        if not email or email in result:
            continue
        try:
            validate_email(email)
        except ValidationError:
            logger.error("Skipped invalid notification email address: %r", email)
            continue
        result.append(email)
    return result


def _config_email(key: str) -> str:
    return str(SystemConfig.get_value(key, default="") or "").strip()


def _requester_email(obj) -> list[str]:
    email = getattr(getattr(obj, "requester", None), "email", "")
    return [email] if email else []


def _first_approver_emails(obj) -> list[str]:
    flag_map = {
        "project": "is_project_approver",
        "non_project": "is_non_project_approver",
        "office": "is_office_approver",
    }
    flag = flag_map.get(getattr(obj, "purchase_type", ""))
    if not flag:
        return []
    return list(
        User.objects.filter(is_active=True, **{f"profile__{flag}": True})
        .exclude(email="")
        .values_list("email", flat=True)
    )


def _final_approver_emails() -> list[str]:
    return list(
        User.objects.filter(is_active=True, profile__is_final_approver=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def _person_name(user) -> str:
    if user is None:
        return "User"
    profile_name = getattr(getattr(user, "profile", None), "display_name", "")
    return profile_name or user.get_full_name() or user.username


def _pr_fields(pr) -> list[tuple[str, object]]:
    return [
        ("Request No.", pr.request_number),
        ("Requester", _person_name(pr.requester)),
        ("Vendor", pr.vendor),
        ("Amount", f"{pr.currency} {pr.total_price:,.2f}"),
        ("Purchase Type", pr.purchase_type_display),
        ("Current Status", pr.human_status_label),
    ]


def _payment_fields(payment) -> list[tuple[str, object]]:
    planned = getattr(payment.purchase_request, "planned_payment_count", 1) if payment.purchase_request_id else 1
    installment = payment.installment_number or 1
    return [
        ("PR Request No.", _pr_number(payment)),
        ("Payment Request No.", payment.request_number),
        ("Payment No.", f"Payment {installment} of {planned}"),
        ("Requester", _person_name(payment.requester)),
        ("Vendor", payment.vendor),
        ("Amount", f"{payment.currency} {payment.total_price:,.2f}"),
        ("Purchase Type", _purchase_type_label(payment)),
        ("Payment Type", _payment_type_label(payment)),
        ("Goods Receive Status", payment.goods_recieve_progress_label),
        ("Current Status", payment.human_status_label),
    ]


def _goods_fields(delivery) -> list[tuple[str, object]]:
    pr = delivery.purchase_request
    return [
        ("Request No.", pr.request_number),
        ("Requester", _person_name(delivery.requester)),
        ("Vendor", delivery.vendor),
        ("Amount", f"{delivery.currency} {delivery.total_price:,.2f}"),
        ("Purchase Type", pr.purchase_type_display),
        ("Goods Receive Status", pr.goods_stage_display),
        ("Current Status", delivery.get_status_display()),
    ]


def _rejection_fields(approver, reason: str) -> list[tuple[str, object]]:
    return [
        ("Rejected By", _person_name(approver)),
        ("Rejection Reason", reason or "No reason provided"),
    ]


def _pr_number(payment) -> str:
    if payment.purchase_request_id and payment.purchase_request:
        return payment.purchase_request.request_number
    return "N/A"


def _payment_type_label(payment) -> str:
    if payment.is_advance_payment:
        return "Advance Payment"
    if payment.purchase_request_id and payment.purchase_request.planned_payment_count > 1:
        return "Progress Payment"
    return "Standard Payment"


def _purchase_type_label(obj) -> str:
    purchase_request = getattr(obj, "purchase_request", None)
    if purchase_request is not None:
        return purchase_request.purchase_type_display
    return str(getattr(obj, "purchase_type", "") or "N/A").replace("_", " ").title()


def _attachment_paths(obj, file_types: set[str]) -> list[str]:
    paths: list[str] = []
    for attachment in obj.attachments.filter(file_type__in=file_types):
        try:
            path = Path(attachment.file.path).resolve()
        except (NotImplementedError, ValueError):
            logger.warning("Attachment #%s has no local filesystem path.", attachment.pk)
            continue
        paths.append(str(path))
        if not path.is_file():
            logger.warning("Attachment file not found for #%s: %s", attachment.pk, path)
    return paths
