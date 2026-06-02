# Generated for учебный проект: промокоды и скидки

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0004_returnrequest_photo"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, help_text="Например: SALE10 или NEWYEAR500.", max_length=40, unique=True, verbose_name="Код промокода")),
                ("name", models.CharField(blank=True, max_length=150, verbose_name="Название акции")),
                ("discount_type", models.CharField(choices=[("percent", "Процент"), ("fixed", "Фиксированная сумма")], default="percent", max_length=20, verbose_name="Тип скидки")),
                ("discount_value", models.DecimalField(decimal_places=2, help_text="Для процента укажите число от 1 до 100. Для фиксированной скидки — сумму в рублях.", max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))], verbose_name="Размер скидки")),
                ("max_discount_amount", models.DecimalField(blank=True, decimal_places=2, help_text="Необязательно. Ограничивает скидку по процентному промокоду.", max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))], verbose_name="Максимальная скидка")),
                ("min_order_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))], verbose_name="Минимальная сумма заказа")),
                ("starts_at", models.DateTimeField(blank=True, null=True, verbose_name="Начало действия")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="Окончание действия")),
                ("max_uses", models.PositiveIntegerField(blank=True, help_text="Оставьте пустым, если лимита нет.", null=True, verbose_name="Лимит использований")),
                ("used_count", models.PositiveIntegerField(default=0, verbose_name="Использовано")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
            ],
            options={
                "verbose_name": "Промокод",
                "verbose_name_plural": "Промокоды",
                "ordering": ["code"],
            },
        ),
        migrations.AddField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))], verbose_name="Скидка"),
        ),
        migrations.AddField(
            model_name="order",
            name="promo_code",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="main.promocode", verbose_name="Промокод"),
        ),
    ]
