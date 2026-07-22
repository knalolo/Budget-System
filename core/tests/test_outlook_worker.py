from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import EmailOutbox


@pytest.mark.django_db
def test_worker_refuses_to_touch_outlook_when_disabled(settings):
    settings.OUTLOOK_EMAIL_ENABLED = False
    EmailOutbox.objects.create(
        to_emails="requester@example.test",
        subject="Disabled test",
        body_html="<p>Disabled</p>",
    )

    with patch("core.management.commands.send_outlook_outbox.subprocess.run") as run:
        with pytest.raises(CommandError, match="Outlook email is disabled"):
            call_command("send_outlook_outbox", send=True)

    run.assert_not_called()


@pytest.mark.django_db
def test_worker_draft_mode_updates_queue_without_send_switch(settings):
    settings.OUTLOOK_EMAIL_ENABLED = True
    item = EmailOutbox.objects.create(
        to_emails="requester@example.test",
        subject="Draft test",
        body_html="<p>Draft</p>",
    )

    with patch(
        "core.management.commands.send_outlook_outbox.subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ) as run:
        call_command("send_outlook_outbox")

    item.refresh_from_db()
    assert item.status == EmailOutbox.STATUS_DRAFTED
    assert item.attempts == 1
    command = run.call_args.args[0]
    assert "-Send" not in command
