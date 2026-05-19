# Generated manually for adding django-autoslug and django-image-uploader-widget support.

from django.db import migrations, models
import autoslug.fields
import catalog.utils


def _build_unique_slug(model, instance, used_slugs):
    base_slug = catalog.utils.cyrillic_slugify(instance.name) or f"{model._meta.model_name}-{instance.pk}"
    slug = base_slug
    index = 2

    while slug in used_slugs or model.objects.exclude(pk=instance.pk).filter(slug=slug).exists():
        slug = f"{base_slug}-{index}"
        index += 1

    used_slugs.add(slug)
    return slug


def populate_existing_slugs(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")

    category_slugs = set()
    for category in Category.objects.order_by("id"):
        category.slug = _build_unique_slug(Category, category, category_slugs)
        category.save(update_fields=["slug"])

    product_slugs = set()
    for product in Product.objects.order_by("id"):
        product.slug = _build_unique_slug(Product, product, product_slugs)
        product.save(update_fields=["slug"])


def clear_slugs(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    Category.objects.update(slug=None)
    Product.objects.update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="slug",
            field=autoslug.fields.AutoSlugField(
                blank=True,
                editable=False,
                max_length=160,
                null=True,
                populate_from="name",
                slugify=catalog.utils.cyrillic_slugify,
                unique=True,
                verbose_name="URL-адрес",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="slug",
            field=autoslug.fields.AutoSlugField(
                blank=True,
                editable=False,
                max_length=220,
                null=True,
                populate_from="name",
                slugify=catalog.utils.cyrillic_slugify,
                unique=True,
                verbose_name="URL-адрес",
            ),
        ),
        migrations.RenameField(
            model_name="productimage",
            old_name="image_url",
            new_name="image",
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(max_length=500, upload_to="products/", verbose_name="Изображение товара"),
        ),
        migrations.RunPython(populate_existing_slugs, clear_slugs),
        migrations.AlterField(
            model_name="category",
            name="slug",
            field=autoslug.fields.AutoSlugField(
                editable=False,
                max_length=160,
                populate_from="name",
                slugify=catalog.utils.cyrillic_slugify,
                unique=True,
                verbose_name="URL-адрес",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="slug",
            field=autoslug.fields.AutoSlugField(
                editable=False,
                max_length=220,
                populate_from="name",
                slugify=catalog.utils.cyrillic_slugify,
                unique=True,
                verbose_name="URL-адрес",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["slug"], name="catalog_pro_slug_6c93d4_idx"),
        ),
    ]
