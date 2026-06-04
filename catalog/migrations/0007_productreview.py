# Generated manually for adding product reviews and ratings.

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0007_stockreservation"),
        ("catalog", "0006_collection_product_collections"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(choices=[(5, "5 — отлично"), (4, "4 — хорошо"), (3, "3 — нормально"), (2, "2 — плохо"), (1, "1 — очень плохо")], validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="Оценка")),
                ("text", models.TextField(help_text="Кратко опишите впечатление от товара, качества, размера или доставки.", max_length=2000, verbose_name="Текст отзыва")),
                ("status", models.CharField(choices=[("pending", "На модерации"), ("published", "Опубликован"), ("rejected", "Отклонён")], db_index=True, default="published", max_length=20, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_reviews", to=settings.AUTH_USER_MODEL, verbose_name="Покупатель")),
                ("order_item", models.ForeignKey(blank=True, help_text="Позиция оплаченного заказа, подтверждающая покупку товара.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="product_reviews", to="main.orderitem", verbose_name="Позиция заказа")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="catalog.product", verbose_name="Товар")),
            ],
            options={
                "verbose_name": "Отзыв о товаре",
                "verbose_name_plural": "Отзывы о товарах",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["product", "status"], name="catalog_pro_product_b9618a_idx"),
                    models.Index(fields=["customer", "created_at"], name="catalog_pro_customer_6aa628_idx"),
                    models.Index(fields=["rating"], name="catalog_pro_rating_4f9aa8_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("product", "customer"), name="unique_product_review_per_customer")],
            },
        ),
    ]
