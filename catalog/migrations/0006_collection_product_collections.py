from django.db import migrations, models
import autoslug.fields
import catalog.utils


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_category_gender"),
    ]

    operations = [
        migrations.CreateModel(
            name="Collection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=120,
                        unique=True,
                        verbose_name="Название коллекции",
                    ),
                ),
                (
                    "slug",
                    autoslug.fields.AutoSlugField(
                        editable=False,
                        max_length=180,
                        populate_from="name",
                        slugify=catalog.utils.cyrillic_slugify,
                        unique=True,
                        verbose_name="URL-адрес",
                    ),
                ),
                (
                    "season",
                    models.CharField(
                        blank=True,
                        help_text="Например: Весна-лето, Осень-зима.",
                        max_length=50,
                        verbose_name="Сезон",
                    ),
                ),
                (
                    "year",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Год выпуска коллекции.",
                        null=True,
                        verbose_name="Год",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Описание коллекции"),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="Показывать на сайте",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Порядок показа"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Дата создания"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Дата обновления"),
                ),
            ],
            options={
                "verbose_name": "Коллекция",
                "verbose_name_plural": "Коллекции",
                "ordering": ["sort_order", "-year", "name"],
            },
        ),
        migrations.AddField(
            model_name="product",
            name="collections",
            field=models.ManyToManyField(
                blank=True,
                help_text="Коллекции, к которым относится товар (например, сезонные или акционные подборки).",
                related_name="products",
                to="catalog.collection",
                verbose_name="Коллекции",
            ),
        ),
        migrations.AddIndex(
            model_name="collection",
            index=models.Index(fields=["slug"], name="catalog_col_slug_a8d5b7_idx"),
        ),
        migrations.AddIndex(
            model_name="collection",
            index=models.Index(fields=["is_active", "sort_order"], name="catalog_col_is_act_2a5f3a_idx"),
        ),
    ]
