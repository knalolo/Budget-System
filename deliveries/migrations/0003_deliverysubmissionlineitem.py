from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_purchaserequestlineitem"),
        ("deliveries", "0002_deliverysubmission_delivered_quantity_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeliverySubmissionLineItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("product", models.CharField(max_length=255)),
                ("ordered_quantity", models.PositiveIntegerField(default=1)),
                ("delivered_quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(choices=[("SGD", "SGD"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP"), ("JPY", "JPY"), ("CNY", "CNY"), ("HKD", "HKD"), ("TWD", "TWD"), ("MYR", "MYR"), ("THB", "THB"), ("INR", "INR"), ("AUD", "AUD"), ("CAD", "CAD"), ("CHF", "CHF"), ("SEK", "SEK"), ("NOK", "NOK"), ("DKK", "DKK"), ("AED", "AED")], max_length=3)),
                ("status", models.CharField(choices=[("partially_delivered", "Partially Delivered"), ("fully_delivered", "Fully Delivered")], default="fully_delivered", max_length=20)),
                ("delivery_submission", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="line_items", to="deliveries.deliverysubmission")),
                ("purchase_request_line_item", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="delivery_line_items", to="orders.purchaserequestlineitem")),
            ],
            options={
                "ordering": ["sequence", "id"],
            },
        ),
    ]
