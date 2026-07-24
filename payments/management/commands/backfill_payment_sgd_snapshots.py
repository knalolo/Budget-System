"""Freeze SGD values for legacy approved payments that predate FX snapshots."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import PaymentRelease


class Command(BaseCommand):
    help = (
        "Populate missing approval-time SGD snapshots on legacy approved payments "
        "using the current FX rate as a one-time baseline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be updated without saving changes.",
        )

    def handle(self, *args, **options):
        payments = PaymentRelease.objects.filter(
            status="approved",
            approved_amount_sgd__isnull=True,
        ).order_by("pk")
        updated = 0
        failed = 0

        for payment in payments.iterator():
            try:
                approved_on = (
                    timezone.localdate(payment.final_decided_at)
                    if payment.final_decided_at
                    else timezone.localdate(payment.updated_at)
                )
                payment.capture_approval_sgd_amount(approved_on=approved_on)
            except RuntimeError as exc:
                failed += 1
                self.stderr.write(
                    f"{payment.request_number}: {exc}"
                )
                continue

            updated += 1
            if not options["dry_run"]:
                payment.save(
                    update_fields=[
                        "approved_amount_sgd",
                        "approval_fx_rate",
                        "approval_fx_date",
                        "updated_at",
                    ]
                )

        action = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {updated} payment snapshot(s); {failed} failed."
            )
        )
