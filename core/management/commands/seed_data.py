"""
Management command: seed_data

Creates default SystemConfig entries and, if the relevant models are
available, default ExpenseCategory and Project records.

Usage:
    python manage.py seed_data
    python manage.py seed_data --reset   # wipe existing configs first
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


# ---------------------------------------------------------------------------
# Default seed data
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_CONFIGS: list[tuple[str, object, str]] = [
    ("po_threshold_eur", 800, "PO approval threshold in EUR"),
    ("po_threshold_sgd", 1300, "PO approval threshold in SGD"),
    ("po_threshold_usd", 900, "PO approval threshold in USD"),
    ("notify_li_mei_email", "", "Notification email for Li Mei"),
    ("notify_jolly_email", "", "Notification email for Jolly"),
    ("notify_jess_email", "", "Notification email for Jess"),
    (
        "credit_platforms",
        ["Digikey", "RS Components", "Element14"],
        "Vendors that support credit-term purchasing",
    ),
]

_DEFAULT_EXPENSE_CATEGORIES: list[str] = [
    "Prototype",
    "Materials",
    "External Testing",
    "External Engineering Service",
    "Certification",
    "Equipment",
    "Accessories",
    "Evaluation",
    "Others",
]

_DEFAULT_PROJECTS: list[tuple[str, str]] = [
    ("MC004574", "Power Cell"),
    ("MC004676", "Display Module"),
    ("MC004680", "U-Shape Sensor"),
    ("GENERAL", "General"),
]


class Command(BaseCommand):
    help = "Seed the database with default system configuration and reference data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing SystemConfig entries before seeding.",
        )

    def handle(self, *args, **options):
        self._seed_system_configs(reset=options["reset"])
        self._seed_expense_categories()
        self._seed_projects()
        self.stdout.write(self.style.SUCCESS("Seed data applied successfully."))

    # ------------------------------------------------------------------
    # SystemConfig
    # ------------------------------------------------------------------

    def _seed_system_configs(self, *, reset: bool) -> None:
        from core.models import SystemConfig

        if reset:
            deleted, _ = SystemConfig.objects.all().delete()
            self.stdout.write(f"  Deleted {deleted} existing SystemConfig entries.")

        created_count = 0
        for key, value, description in _DEFAULT_SYSTEM_CONFIGS:
            _, created = SystemConfig.objects.get_or_create(
                key=key,
                defaults={
                    "description": description,
                },
            )
            if created:
                # Use the class method to ensure value is JSON-encoded.
                SystemConfig.set_value(key, value, description)
                created_count += 1
                self.stdout.write(f"  Created SystemConfig: {key}")
            else:
                self.stdout.write(f"  Skipped (exists): {key}")

        self.stdout.write(f"SystemConfig: {created_count} created.")

    # ------------------------------------------------------------------
    # ExpenseCategory
    # ------------------------------------------------------------------

    def _seed_expense_categories(self) -> None:
        try:
            from orders.models import ExpenseCategory  # noqa: PLC0415
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "orders.ExpenseCategory not available yet — skipping."
                )
            )
            return

        created_count = 0
        for name in _DEFAULT_EXPENSE_CATEGORIES:
            _, created = ExpenseCategory.objects.get_or_create(name=name)
            if created:
                created_count += 1
                self.stdout.write(f"  Created ExpenseCategory: {name}")
            else:
                self.stdout.write(f"  Skipped (exists): ExpenseCategory '{name}'")

        self.stdout.write(f"ExpenseCategory: {created_count} created.")

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------

    def _seed_projects(self) -> None:
        try:
            from orders.models import Project  # noqa: PLC0415
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "orders.Project not available yet — skipping."
                )
            )
            return

        created_count = 0
        for mc_number, name in _DEFAULT_PROJECTS:
            _, created = Project.objects.get_or_create(
                mc_number=mc_number,
                defaults={"name": name},
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created Project: {mc_number} - {name}")
            else:
                self.stdout.write(f"  Skipped (exists): Project '{mc_number}'")

        self.stdout.write(f"Project: {created_count} created.")
