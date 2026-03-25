from django.db import migrations


def sync_linked_payment_numbers(apps, schema_editor):
    PaymentRelease = apps.get_model("payments", "PaymentRelease")

    for payment in PaymentRelease.objects.exclude(purchase_request__isnull=True):
        purchase_request = payment.purchase_request
        if not purchase_request or not purchase_request.request_number:
            continue

        desired_number = purchase_request.request_number.replace("PR-", "RP-", 1)
        if payment.request_number == desired_number:
            continue

        conflict = PaymentRelease.objects.filter(request_number=desired_number).exclude(
            pk=payment.pk
        )
        if conflict.exists():
            continue

        payment.request_number = desired_number
        payment.save(update_fields=["request_number"])


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sync_linked_payment_numbers, migrations.RunPython.noop),
    ]
