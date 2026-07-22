import json
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from core.models import EmailOutbox


class Command(BaseCommand):
    help = "Send pending EmailOutbox rows through the local Outlook desktop PowerShell worker."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument(
            "--send",
            action="store_true",
            help="Actually send via Outlook. Without this, messages are saved as drafts.",
        )
        parser.add_argument("--display", action="store_true", help="Display draft windows when not sending.")
        parser.add_argument("--status", default=EmailOutbox.STATUS_PENDING)

    def handle(self, *args, **options):
        if not settings.OUTLOOK_EMAIL_ENABLED:
            raise CommandError(
                "Outlook email is disabled. Set OUTLOOK_EMAIL_ENABLED=True on the Host only after approval."
            )

        script_path = Path(settings.BASE_DIR) / "scripts" / "outlook_send_shared_mail.ps1"
        if not script_path.exists():
            raise CommandError(f"Outlook script not found: {script_path}")

        rows = list(
            EmailOutbox.objects.filter(status=options["status"]).order_by("created_at")[: options["limit"]]
        )
        if not rows:
            self.stdout.write("No EmailOutbox rows to process.")
            return

        for item in rows:
            claimed = EmailOutbox.objects.filter(
                pk=item.pk,
                status=options["status"],
            ).update(
                status=EmailOutbox.STATUS_PROCESSING,
                attempts=F("attempts") + 1,
                last_error="",
            )
            if not claimed:
                continue
            item.refresh_from_db()

            temp_html = None
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
                    handle.write(item.body_html)
                    temp_html = Path(handle.name)

                command = [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-FromMailbox",
                    item.from_mailbox,
                    "-To",
                    item.to_emails,
                    "-Subject",
                    item.subject,
                    "-HtmlBodyPath",
                    str(temp_html),
                    "-AttachmentsJson",
                    json.dumps(item.attachment_paths),
                ]
                if item.cc_emails:
                    command.extend(["-Cc", item.cc_emails])
                if options["send"]:
                    command.append("-Send")
                elif options["display"]:
                    command.append("-Display")

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )

                if result.returncode == 0:
                    item.status = EmailOutbox.STATUS_SENT if options["send"] else EmailOutbox.STATUS_DRAFTED
                    item.processed_at = timezone.now()
                    item.last_error = ""
                    item.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
                    self.stdout.write(self.style.SUCCESS(f"{item.get_status_display()}: EmailOutbox #{item.pk}"))
                else:
                    item.status = EmailOutbox.STATUS_FAILED
                    item.last_error = (result.stderr or result.stdout or "Unknown Outlook worker error").strip()
                    item.save(update_fields=["status", "last_error", "updated_at"])
                    self.stderr.write(self.style.ERROR(f"Failed EmailOutbox #{item.pk}: {item.last_error}"))
            except Exception as exc:  # noqa: BLE001
                item.status = EmailOutbox.STATUS_FAILED
                item.last_error = str(exc)
                item.save(update_fields=["status", "last_error", "updated_at"])
                self.stderr.write(self.style.ERROR(f"Failed EmailOutbox #{item.pk}: {item.last_error}"))
            finally:
                if temp_html and temp_html.exists():
                    try:
                        temp_html.unlink()
                    except FileNotFoundError:
                        pass
