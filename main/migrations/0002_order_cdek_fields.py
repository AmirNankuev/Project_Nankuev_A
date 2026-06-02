# Generated manually for CDEK integration.

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="delivery_type",
            field=models.CharField(
                choices=[
                    ("courier", "Курьер"),
                    ("pickup", "Самовывоз"),
                    ("post", "Почта"),
                    ("cdek_courier", "СДЭК курьером"),
                    ("cdek_pickup", "СДЭК пункт выдачи"),
                ],
                max_length=50,
                verbose_name="Способ доставки",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                validators=[MinValueValidator(Decimal("0.00"))],
                verbose_name="Стоимость доставки",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_city_code",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Код города СДЭК"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_tariff_code",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Код тарифа СДЭК"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_delivery_period_min",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Минимальный срок доставки СДЭК, дней"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_delivery_period_max",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Максимальный срок доставки СДЭК, дней"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_uuid",
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name="UUID заказа в СДЭК"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_status",
            field=models.CharField(
                choices=[
                    ("not_sent", "Не отправлен"),
                    ("created", "Создан в СДЭК"),
                    ("error", "Ошибка СДЭК"),
                    ("demo", "Демо-режим"),
                ],
                default="not_sent",
                max_length=30,
                verbose_name="Статус интеграции СДЭК",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_error",
            field=models.TextField(blank=True, verbose_name="Ошибка СДЭК"),
        ),
        migrations.AddField(
            model_name="order",
            name="cdek_response",
            field=models.JSONField(blank=True, null=True, verbose_name="Ответ СДЭК"),
        ),
    ]
