import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetregistration",
            name="payment_release",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="asset_registrations",
                to="payments.paymentrelease",
            ),
        ),
    ]
