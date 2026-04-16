from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_purchaserequest_ordered_quantity_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseRequestLineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("product", models.CharField(max_length=255)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(choices=[("SGD", "SGD"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP"), ("JPY", "JPY"), ("CNY", "CNY"), ("HKD", "HKD"), ("TWD", "TWD"), ("MYR", "MYR"), ("THB", "THB"), ("INR", "INR"), ("AUD", "AUD"), ("CAD", "CAD"), ("CHF", "CHF"), ("SEK", "SEK"), ("NOK", "NOK"), ("DKK", "DKK"), ("AED", "AED")], max_length=3)),
                ("purchase_request", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="line_items", to="orders.purchaserequest")),
            ],
            options={
                "ordering": ["sequence", "id"],
            },
        ),
    ]
