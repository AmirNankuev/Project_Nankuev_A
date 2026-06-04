from decimal import Decimal, ROUND_HALF_UP

from autoslug import AutoSlugField
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Avg, Q

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
    class Gender(models.TextChoices):
        MALE = "male", "Мужское"
        FEMALE = "female", "Женское"
        UNISEX = "unisex", "Унисекс"

    name = models.CharField(
        "Название категории",
        max_length=100,
        unique=True,
    )
    gender = models.CharField(
        "Пол",
        max_length=20,
        choices=Gender.choices,
        default=Gender.UNISEX,
        db_index=True,
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


class Collection(models.Model):
    name = models.CharField(
        "Название коллекции",
        max_length=120,
        unique=True,
    )
    slug = AutoSlugField(
        "URL-адрес",
        populate_from="name",
        slugify=cyrillic_slugify,
        unique=True,
        max_length=180,
    )
    season = models.CharField(
        "Сезон",
        max_length=50,
        blank=True,
        help_text="Например: Весна-лето, Осень-зима.",
    )
    year = models.PositiveSmallIntegerField(
        "Год",
        blank=True,
        null=True,
        help_text="Год выпуска коллекции.",
    )
    description = models.TextField(
        "Описание коллекции",
        blank=True,
    )
    is_active = models.BooleanField(
        "Показывать на сайте",
        default=True,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(
        "Порядок показа",
        default=0,
    )
    created_at = models.DateTimeField(
        "Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "Дата обновления",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Коллекция"
        verbose_name_plural = "Коллекции"
        ordering = ["sort_order", "-year", "name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "sort_order"]),
        ]

    @property
    def display_period(self):
        if self.season and self.year:
            return f"{self.season} {self.year}"
        if self.season:
            return self.season
        if self.year:
            return str(self.year)
        return ""

    def __str__(self):
        period = self.display_period
        if period:
            return f"{self.name} — {period}"
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
    collections = models.ManyToManyField(
        Collection,
        verbose_name="Коллекции",
        related_name="products",
        blank=True,
        help_text="Коллекции, к которым относится товар (например, сезонные или акционные подборки).",
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

    @property
    def reviews_count(self):
        annotated_count = getattr(self, "published_reviews_count", None)
        if annotated_count is not None:
            return annotated_count

        return self.reviews.filter(status=ProductReview.Status.PUBLISHED).count()

    @property
    def average_rating(self):
        annotated_rating = getattr(self, "published_average_rating", None)
        if annotated_rating is not None:
            return annotated_rating or 0

        return self.reviews.filter(
            status=ProductReview.Status.PUBLISHED
        ).aggregate(value=Avg("rating"))["value"] or 0

    @property
    def average_rating_label(self):
        rating = self.average_rating
        if not rating:
            return "Нет оценок"

        rating_value = Decimal(str(rating)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{rating_value} из 5"

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

class ProductReview(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        PUBLISHED = "published", "Опубликован"
        REJECTED = "rejected", "Отклонён"

    RATING_CHOICES = [
        (5, "5 — отлично"),
        (4, "4 — хорошо"),
        (3, "3 — нормально"),
        (2, "2 — плохо"),
        (1, "1 — очень плохо"),
    ]

    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Покупатель",
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    order_item = models.ForeignKey(
        "main.OrderItem",
        verbose_name="Позиция заказа",
        on_delete=models.SET_NULL,
        related_name="product_reviews",
        blank=True,
        null=True,
        help_text="Позиция оплаченного заказа, подтверждающая покупку товара.",
    )
    rating = models.PositiveSmallIntegerField(
        "Оценка",
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    text = models.TextField(
        "Текст отзыва",
        max_length=2000,
        help_text="Кратко опишите впечатление от товара, качества, размера или доставки.",
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PUBLISHED,
        db_index=True,
    )
    created_at = models.DateTimeField(
        "Дата создания",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "Дата обновления",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Отзыв о товаре"
        verbose_name_plural = "Отзывы о товарах"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "customer"],
                name="unique_product_review_per_customer",
            )
        ]
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["rating"]),
        ]

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def rating_label(self):
        return f"{self.rating} из 5"

    @property
    def author_name(self):
        full_name = getattr(self.customer, "full_name", "") or self.customer.get_full_name()
        return full_name or self.customer.username

    def __str__(self):
        return f"{self.product.name}: {self.rating} из 5 — {self.customer}"

