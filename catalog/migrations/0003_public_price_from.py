# Generated manually: public prices are displayed as "от ... ₽" from variant prices.

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_autoslug_and_image_upload"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Служебное поле: на сайте покупателям не показывается. "
                    "Публичная цена берётся из цен вариантов товара."
                ),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Служебная базовая цена",
            ),
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="price_modifier",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Полная публичная цена конкретного размера/цвета. "
                    "Из этих значений на сайте считается цена «от»."
                ),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Цена варианта",
            ),
        ),
    ]
