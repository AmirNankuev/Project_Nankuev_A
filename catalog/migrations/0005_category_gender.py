from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_variant_pricing_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="gender",
            field=models.CharField(
                choices=[
                    ("male", "Мужское"),
                    ("female", "Женское"),
                    ("unisex", "Унисекс"),
                ],
                db_index=True,
                default="unisex",
                max_length=20,
                verbose_name="Пол",
            ),
        ),
    ]
