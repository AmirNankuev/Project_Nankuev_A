# Generated manually: variant prices can be calculated by markup or fixed site price.

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def mark_existing_variant_prices_as_fixed(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    ProductVariant.objects.filter(site_price__gt=Decimal("0.00")).update(pricing_type="fixed")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_public_price_from"),
    ]

    operations = [
        migrations.RenameField(
            model_name="productvariant",
            old_name="price_modifier",
            new_name="site_price",
        ),
        migrations.AddField(
            model_name="productvariant",
            name="pricing_type",
            field=models.CharField(
                choices=[
                    ("markup", "Наценка от базовой цены"),
                    ("fixed", "Готовая цена на сайте"),
                ],
                default="markup",
                help_text=(
                    "Выберите: считать цену через процентную наценку от базовой закупочной "
                    "цены товара или указать готовую цену для сайта вручную."
                ),
                max_length=20,
                verbose_name="Способ расчёта цены",
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="markup_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Используется при способе «Наценка от базовой цены». "
                    "Например: 40 означает базовая цена + 40%."
                ),
                max_digits=7,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Наценка, %",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Внутренняя закупочная цена товара. На сайте покупателям не показывается. "
                    "Публичная цена рассчитывается в вариантах товара."
                ),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Базовая цена (закупка)",
            ),
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="site_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Используется при способе «Готовая цена на сайте». "
                    "Это цена, которую увидит покупатель для конкретного размера/цвета."
                ),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Готовая цена на сайте",
            ),
        ),
        migrations.RunPython(mark_existing_variant_prices_as_fixed, migrations.RunPython.noop),
    ]
