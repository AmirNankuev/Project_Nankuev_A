# Generated manually for stock reservation support.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_category_gender"),
        ("main", "0006_shopsettings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="shopsettings",
            name="reservation_hold_minutes",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Сколько минут товар удерживается за покупателем, пока он завершает онлайн-оплату.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(1440),
                ],
                verbose_name="Время резервирования товара, минут",
            ),
        ),
        migrations.CreateModel(
            name="StockReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name="Количество")),
                ("status", models.CharField(choices=[("active", "Зарезервирован"), ("confirmed", "Подтверждён"), ("released", "Освобождён")], db_index=True, default="active", max_length=20, verbose_name="Статус резерва")),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, help_text="Для онлайн-оплаты: время, после которого резерв автоматически освобождается.", null=True, verbose_name="Действует до")),
                ("confirmed_at", models.DateTimeField(blank=True, null=True, verbose_name="Подтверждён")),
                ("released_at", models.DateTimeField(blank=True, null=True, verbose_name="Освобождён")),
                ("release_reason", models.CharField(blank=True, max_length=100, verbose_name="Причина освобождения")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to=settings.AUTH_USER_MODEL, verbose_name="Покупатель")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reservations", to="main.order", verbose_name="Заказ")),
                ("order_item", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="reservation", to="main.orderitem", verbose_name="Позиция заказа")),
                ("product_variant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservations", to="catalog.productvariant", verbose_name="Вариант товара")),
            ],
            options={
                "verbose_name": "Резерв товара",
                "verbose_name_plural": "Резервы товаров",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status", "expires_at"], name="main_stockr_status_f83531_idx"),
                    models.Index(fields=["product_variant", "status"], name="main_stockr_product_b9f87f_idx"),
                    models.Index(fields=["order", "status"], name="main_stockr_order_i_2b7f74_idx"),
                ],
            },
        ),
    ]
