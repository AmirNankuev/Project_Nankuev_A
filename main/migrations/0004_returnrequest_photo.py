from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_order_yookassa_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="returnrequest",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="returns/", verbose_name="Фото товара"),
        ),
    ]
