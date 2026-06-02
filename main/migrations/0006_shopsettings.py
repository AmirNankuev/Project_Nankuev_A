# Generated for учебный проект: настройки магазина

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0005_promocode_order_discount"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("singleton_name", models.CharField(default="main", editable=False, max_length=30, unique=True, verbose_name="Служебное имя")),
                ("return_period_days", models.PositiveIntegerField(default=14, help_text="Количество дней после оформления заказа, в течение которых покупатель может создать заявку на возврат.", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)], verbose_name="Срок возврата, дней")),
                ("free_delivery_from", models.DecimalField(blank=True, decimal_places=2, help_text="Оставьте пустым или укажите 0, если бесплатная доставка отключена.", max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))], verbose_name="Бесплатная доставка от суммы")),
                ("shop_phone", models.CharField(blank=True, max_length=50, verbose_name="Телефон магазина")),
                ("shop_email", models.EmailField(blank=True, max_length=254, verbose_name="Email магазина")),
                ("delivery_terms", models.TextField(blank=True, verbose_name="Условия доставки")),
                ("payment_terms", models.TextField(blank=True, verbose_name="Условия оплаты")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
            ],
            options={
                "verbose_name": "Настройки магазина",
                "verbose_name_plural": "Настройки магазина",
            },
        ),
    ]
