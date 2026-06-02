# Generated manually for YooKassa test payment integration.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0002_order_cdek_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("yookassa_card", "ЮKassa — банковская карта"),
                    ("yookassa_sbp", "ЮKassa — СБП"),
                    ("card_online", "Карта онлайн"),
                    ("cash_on_delivery", "Оплата при получении"),
                    ("sbp", "СБП"),
                ],
                max_length=50,
                verbose_name="Способ оплаты",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="yookassa_payment_id",
            field=models.CharField(blank=True, max_length=120, null=True, verbose_name="ID платежа ЮKassa"),
        ),
        migrations.AddField(
            model_name="order",
            name="yookassa_payment_status",
            field=models.CharField(
                choices=[
                    ("not_created", "Не создан"),
                    ("pending", "Ожидает оплаты"),
                    ("waiting_for_capture", "Ожидает подтверждения"),
                    ("succeeded", "Успешно оплачен"),
                    ("canceled", "Отменён"),
                    ("error", "Ошибка ЮKassa"),
                ],
                default="not_created",
                max_length=40,
                verbose_name="Статус платежа ЮKassa",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="yookassa_confirmation_url",
            field=models.URLField(blank=True, max_length=1000, verbose_name="Ссылка на оплату ЮKassa"),
        ),
        migrations.AddField(
            model_name="order",
            name="yookassa_error",
            field=models.TextField(blank=True, verbose_name="Ошибка ЮKassa"),
        ),
        migrations.AddField(
            model_name="order",
            name="yookassa_response",
            field=models.JSONField(blank=True, null=True, verbose_name="Ответ ЮKassa"),
        ),
    ]
