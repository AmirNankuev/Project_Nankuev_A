from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class CustomerProfile(models.Model):
    ACCOUNT_STATUS_CHOICES = [
        ("active", "Активен"),
        ("blocked", "Заблокирован"),
        ("deleted", "Удалён"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(
        "Телефон",
        max_length=255,
        unique=True,
    )
    account_status = models.CharField(
        "Статус аккаунта",
        max_length=30,
        choices=ACCOUNT_STATUS_CHOICES,
        default="active",
    )
    registration_date = models.DateTimeField(
        "Дата регистрации",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Покупатель"
        verbose_name_plural = "Покупатели"

    def __str__(self):
        full_name = self.user.get_full_name()

        if full_name:
            return f"{full_name} ({self.user.email})"

        return self.user.email or self.user.username


def generate_order_number():
    return f"ORDER-{uuid4().hex[:10].upper()}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("created", "Создан"),
        ("paid", "Оплачен"),
        ("processing", "В обработке"),
        ("assembled", "Собран"),
        ("shipped", "Передан в доставку"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменён"),
        ("returned", "Возвращён"),
    ]

    DELIVERY_TYPE_CHOICES = [
        ("courier", "Курьер"),
        ("pickup", "Самовывоз"),
        ("post", "Почта"),
        ("cdek_courier", "СДЭК курьером"),
        ("cdek_pickup", "СДЭК пункт выдачи"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("yookassa_card", "ЮKassa — банковская карта"),
        ("yookassa_sbp", "ЮKassa — СБП"),
        ("card_online", "Карта онлайн"),
        ("cash_on_delivery", "Оплата при получении"),
        ("sbp", "СБП"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Ожидает оплаты"),
        ("paid", "Оплачен"),
        ("failed", "Ошибка оплаты"),
        ("refunded", "Возвращён"),
    ]

    order_number = models.CharField(
        "Номер заказа",
        max_length=50,
        unique=True,
        default=generate_order_number,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Покупатель",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        "Статус заказа",
        max_length=50,
        choices=STATUS_CHOICES,
        default="created",
    )
    total_amount = models.DecimalField(
        "Итоговая сумма",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    delivery_address = models.TextField(
        "Адрес доставки",
    )
    delivery_type = models.CharField(
        "Способ доставки",
        max_length=50,
        choices=DELIVERY_TYPE_CHOICES,
    )
    payment_method = models.CharField(
        "Способ оплаты",
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
    )
    payment_status = models.CharField(
        "Статус оплаты",
        max_length=30,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending",
    )
    tracking_number = models.CharField(
        "Трек-номер доставки",
        max_length=100,
        blank=True,
        null=True,
    )
    delivery_price = models.DecimalField(
        "Стоимость доставки",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    cdek_city_code = models.PositiveIntegerField(
        "Код города СДЭК",
        blank=True,
        null=True,
    )
    cdek_tariff_code = models.PositiveIntegerField(
        "Код тарифа СДЭК",
        blank=True,
        null=True,
    )
    cdek_delivery_period_min = models.PositiveIntegerField(
        "Минимальный срок доставки СДЭК, дней",
        blank=True,
        null=True,
    )
    cdek_delivery_period_max = models.PositiveIntegerField(
        "Максимальный срок доставки СДЭК, дней",
        blank=True,
        null=True,
    )
    cdek_uuid = models.CharField(
        "UUID заказа в СДЭК",
        max_length=100,
        blank=True,
        null=True,
    )
    cdek_status = models.CharField(
        "Статус интеграции СДЭК",
        max_length=30,
        default="not_sent",
        choices=[
            ("not_sent", "Не отправлен"),
            ("created", "Создан в СДЭК"),
            ("error", "Ошибка СДЭК"),
            ("demo", "Демо-режим"),
        ],
    )
    cdek_error = models.TextField(
        "Ошибка СДЭК",
        blank=True,
    )
    cdek_response = models.JSONField(
        "Ответ СДЭК",
        blank=True,
        null=True,
    )
    yookassa_payment_id = models.CharField(
        "ID платежа ЮKassa",
        max_length=120,
        blank=True,
        null=True,
    )
    yookassa_payment_status = models.CharField(
        "Статус платежа ЮKassa",
        max_length=40,
        default="not_created",
        choices=[
            ("not_created", "Не создан"),
            ("pending", "Ожидает оплаты"),
            ("waiting_for_capture", "Ожидает подтверждения"),
            ("succeeded", "Успешно оплачен"),
            ("canceled", "Отменён"),
            ("error", "Ошибка ЮKassa"),
        ],
    )
    yookassa_confirmation_url = models.URLField(
        "Ссылка на оплату ЮKassa",
        max_length=1000,
        blank=True,
    )
    yookassa_error = models.TextField(
        "Ошибка ЮKassa",
        blank=True,
    )
    yookassa_response = models.JSONField(
        "Ответ ЮKassa",
        blank=True,
        null=True,
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
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["payment_status"]),
        ]

    def recalculate_total(self):
        items_total = sum(item.subtotal for item in self.items.all())
        self.total_amount = items_total + (self.delivery_price or Decimal("0.00"))
        self.save(update_fields=["total_amount"])

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name="Заказ",
        on_delete=models.CASCADE,
        related_name="items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        verbose_name="Вариант товара",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField(
        "Количество",
        validators=[
            MinValueValidator(1),
        ],
    )
    unit_price = models.DecimalField(
        "Цена за единицу",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    subtotal = models.DecimalField(
        "Промежуточная сумма",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def save(self, *args, **kwargs):
        if self.unit_price == Decimal("0.00"):
            self.unit_price = self.product_variant.final_price

        self.subtotal = self.unit_price * self.quantity

        super().save(*args, **kwargs)

        self.order.recalculate_total()

    def __str__(self):
        return f"{self.product_variant} × {self.quantity}"


class ReturnRequest(models.Model):
    CONDITION_CHOICES = [
        ("new", "Новый"),
        ("worn", "Ношенный"),
        ("damaged", "С дефектом"),
    ]

    STATUS_CHOICES = [
        ("requested", "Запрошен"),
        ("approved", "Одобрен"),
        ("rejected", "Отклонён"),
        ("completed", "Завершён"),
    ]

    order_item = models.OneToOneField(
        OrderItem,
        verbose_name="Позиция заказа",
        on_delete=models.CASCADE,
        related_name="return_request",
    )
    reason = models.TextField(
        "Причина возврата",
    )
    condition = models.CharField(
        "Состояние товара",
        max_length=50,
        choices=CONDITION_CHOICES,
    )
    status = models.CharField(
        "Статус возврата",
        max_length=30,
        choices=STATUS_CHOICES,
        default="requested",
    )
    refund_amount = models.DecimalField(
        "Сумма возврата",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )
    created_at = models.DateTimeField(
        "Дата подачи заявки",
        auto_now_add=True,
    )
    resolved_at = models.DateTimeField(
        "Дата завершения обработки",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Возврат"
        verbose_name_plural = "Возвраты"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Возврат по позиции заказа #{self.order_item_id}"


class CartItem(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Покупатель",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        verbose_name="Вариант товара",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(
        "Количество",
        validators=[
            MinValueValidator(1),
        ],
    )
    added_at = models.DateTimeField(
        "Дата добавления",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Товар в корзине"
        verbose_name_plural = "Корзина"
        ordering = ["-added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product_variant"],
                name="unique_customer_product_variant_cart",
            )
        ]

    def __str__(self):
        return f"{self.customer} — {self.product_variant} × {self.quantity}"