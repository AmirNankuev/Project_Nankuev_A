from decimal import Decimal, ROUND_HALF_UP

from autoslug import AutoSlugField
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from .utils import cyrillic_slugify


class Brand(models.Model):
    name = models.CharField(
        "Название бренда",
        max_length=100,
        unique=True,
    )
    description = models.TextField(
        "Описание бренда",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренды"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(
        "Название категории",
        max_length=100,
        unique=True,
    )
    slug = AutoSlugField(
        "URL-адрес",
        populate_from="name",
        slugify=cyrillic_slugify,
        unique=True,
        max_length=160,
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="Родительская категория",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="children",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name


class Color(models.Model):
    name = models.CharField(
        "Название цвета",
        max_length=50,
        unique=True,
    )
    hex_code = models.CharField(
        "HEX-код цвета",
        max_length=7,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message="HEX-код должен быть в формате #000000",
            )
        ],
    )

    class Meta:
        verbose_name = "Цвет"
        verbose_name_plural = "Цвета"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    article = models.CharField(
        "Артикул",
        max_length=50,
        unique=True,
    )
    name = models.CharField(
        "Название товара",
        max_length=255,
    )
    slug = AutoSlugField(
        "URL-адрес",
        populate_from="name",
        slugify=cyrillic_slugify,
        unique=True,
        max_length=220,
    )
    description = models.TextField(
        "Описание товара",
        blank=True,
        null=True,
    )
    brand = models.ForeignKey(
        Brand,
        verbose_name="Бренд",
        on_delete=models.PROTECT,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        verbose_name="Категория",
        on_delete=models.PROTECT,
        related_name="products",
    )
    price = models.DecimalField(
        "Базовая цена (закупка)",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Внутренняя закупочная цена товара. На сайте покупателям не показывается. "
            "Публичная цена рассчитывается в вариантах товара."
        ),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    is_active = models.BooleanField(
        "Доступен для продажи",
        default=True,
    )
    created_at = models.DateTimeField(
        "Дата создания",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["article"]),
            models.Index(fields=["name"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    @property
    def price_from(self):
        variants = getattr(self, "prepared_variants", None)

        if variants is None:
            variants = self.variants.all()

        prices = []
        for variant in variants:
            final_price = variant.final_price
            if final_price and final_price > Decimal("0.00"):
                prices.append(final_price)

        if prices:
            return min(prices)

        return None

    @property
    def price_from_label(self):
        if self.price_from is None:
            return "Цена по запросу"

        return f"от {self.price_from} ₽"

    def __str__(self):
        return f"{self.name} ({self.article})"


class ProductVariant(models.Model):
    class PricingType(models.TextChoices):
        MARKUP = "markup", "Наценка от базовой цены"
        FIXED = "fixed", "Готовая цена на сайте"

    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="variants",
    )
    color = models.ForeignKey(
        Color,
        verbose_name="Цвет",
        on_delete=models.PROTECT,
        related_name="variants",
    )
    size = models.CharField(
        "Размер",
        max_length=20,
    )
    quantity = models.PositiveIntegerField(
        "Количество на складе",
        default=0,
    )
    pricing_type = models.CharField(
        "Способ расчёта цены",
        max_length=20,
        choices=PricingType.choices,
        default=PricingType.MARKUP,
        help_text=(
            "Выберите: считать цену через процентную наценку от базовой закупочной "
            "цены товара или указать готовую цену для сайта вручную."
        ),
    )
    markup_percent = models.DecimalField(
        "Наценка, %",
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Используется при способе «Наценка от базовой цены». "
            "Например: 40 означает базовая цена + 40%."
        ),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    site_price = models.DecimalField(
        "Готовая цена на сайте",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Используется при способе «Готовая цена на сайте». "
            "Это цена, которую увидит покупатель для конкретного размера/цвета."
        ),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    class Meta:
        verbose_name = "Вариант товара"
        verbose_name_plural = "Варианты товаров"
        ordering = ["product", "color", "size"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "color", "size"],
                name="unique_product_color_size",
            )
        ]

    @property
    def final_price(self):
        if self.pricing_type == self.PricingType.FIXED:
            if self.site_price and self.site_price > Decimal("0.00"):
                return self.site_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return Decimal("0.00")

        base_price = self.product.price if self.product_id and self.product.price else Decimal("0.00")
        multiplier = Decimal("1.00") + (self.markup_percent / Decimal("100"))
        return (base_price * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def public_price_label(self):
        if self.final_price and self.final_price > Decimal("0.00"):
            return f"{self.final_price} ₽"
        return "Цена не задана"

    def __str__(self):
        return f"{self.product.name} — {self.color.name}, размер {self.size}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        "Изображение товара",
        upload_to="products/",
        max_length=500,
    )
    is_main = models.BooleanField(
        "Главное изображение",
        default=False,
    )
    sort_order = models.PositiveIntegerField(
        "Порядок сортировки",
        default=0,
    )

    class Meta:
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_main=True),
                name="one_main_image_per_product",
            )
        ]

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return ""

    def __str__(self):
        return f"Изображение товара: {self.product.name}"
