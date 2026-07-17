from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_purchaserequest_purchase_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="execution_mode",
            field=models.CharField(
                choices=[
                    ("payment_first", "Pay first"),
                    ("delivery_first", "Goods receive first"),
                ],
                default="delivery_first",
                max_length=20,
            ),
        ),
    ]
