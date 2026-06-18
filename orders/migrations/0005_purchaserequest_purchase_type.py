from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_purchaserequestlineitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="purchase_type",
            field=models.CharField(
                choices=[
                    ("project", "Project"),
                    ("non_project", "Non-Project"),
                    ("office", "Office"),
                ],
                default="project",
                max_length=20,
            ),
        ),
    ]
