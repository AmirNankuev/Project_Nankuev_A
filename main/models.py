from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


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



class PromoCode(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Процент"
        FIXED = "fixed", "Фиксированная сумма"

    code = models.CharField(
        "Код промокода",
        max_length=40,
        unique=True,
        db_index=True,
        help_text="Например: SALE10 или NEWYEAR500.",
    )
    name = models.CharField(
        "Название акции",
        max_length=150,
        blank=True,
    )
    discount_type = models.CharField(
        "Тип скидки",
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    discount_value = models.DecimalField(
        "Размер скидки",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Для процента укажите число от 1 до 100. Для фиксированной скидки — сумму в рублях.",
    )
    max_discount_amount = models.DecimalField(
        "Максимальная скидка",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Необязательно. Ограничивает скидку по процентному промокоду.",
    )
    min_order_amount = models.DecimalField(
        "Минимальная сумма заказа",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    starts_at = models.DateTimeField(
        "Начало действия",
        blank=True,
        null=True,
    )
    ends_at = models.DateTimeField(
        "Окончание действия",
        blank=True,
        null=True,
    )
    max_uses = models.PositiveIntegerField(
        "Лимит использований",
        blank=True,
        null=True,
        help_text="Оставьте пустым, если лимита нет.",
    )
    used_count = models.PositiveIntegerField(
        "Использовано",
        default=0,
    )
    is_active = models.BooleanField(
        "Активен",
        default=True,
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
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"
        ordering = ["code"]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

    @property
    def has_usage_limit_reached(self):
        return self.max_uses is not None and self.used_count >= self.max_uses

    def is_valid_for_amount(self, order_amount, now=None):
        return self.get_unavailable_reason(order_amount, now=now) == ""

    def get_unavailable_reason(self, order_amount, now=None):
        now = now or timezone.now()
        order_amount = order_amount or Decimal("0.00")

        if not self.is_active:
            return "Промокод отключён."
        if self.starts_at and self.starts_at > now:
            return "Промокод ещё не начал действовать."
        if self.ends_at and self.ends_at < now:
            return "Срок действия промокода истёк."
        if self.has_usage_limit_reached:
            return "Промокод уже использован максимальное количество раз."
        if order_amount < self.min_order_amount:
            return f"Промокод действует от суммы {self.min_order_amount} ₽."
        return ""

    def calculate_discount(self, order_amount):
        order_amount = order_amount or Decimal("0.00")

        if order_amount <= Decimal("0.00"):
            return Decimal("0.00")

        if self.discount_type == self.DiscountType.FIXED:
            discount = self.discount_value
        else:
            discount = order_amount * self.discount_value / Decimal("100")
            if self.max_discount_amount is not None:
                discount = min(discount, self.max_discount_amount)

        discount = max(Decimal("0.00"), min(discount, order_amount))
        return discount.quantize(Decimal("0.01"))


class ShopSettings(models.Model):
    singleton_name = models.CharField(
        "Служебное имя",
        max_length=30,
        default="main",
        unique=True,
        editable=False,
    )
    return_period_days = models.PositiveIntegerField(
        "Срок возврата, дней",
        default=14,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Количество дней после оформления заказа, в течение которых покупатель может создать заявку на возврат.",
    )
    reservation_hold_minutes = models.PositiveIntegerField(
        "Время резервирования товара, минут",
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text="Сколько минут товар удерживается за покупателем, пока он завершает онлайн-оплату.",
    )
    free_delivery_from = models.DecimalField(
        "Бесплатная доставка от суммы",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Оставьте пустым или укажите 0, если бесплатная доставка отключена.",
    )
    shop_phone = models.CharField(
        "Телефон магазина",
        max_length=50,
        blank=True,
    )
    shop_email = models.EmailField(
        "Email магазина",
        blank=True,
    )
    delivery_terms = models.TextField(
        "Условия доставки",
        blank=True,
    )
    payment_terms = models.TextField(
        "Условия оплаты",
        blank=True,
    )
    updated_at = models.DateTimeField(
        "Дата обновления",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Настройки магазина"
        verbose_name_plural = "Настройки магазина"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.singleton_name = "main"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return "Настройки магазина"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"singleton_name": "main"})
        return obj

    @property
    def free_delivery_enabled(self):
        return bool(self.free_delivery_from and self.free_delivery_from > Decimal("0.00"))


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
    promo_code = models.ForeignKey(
        PromoCode,
        verbose_name="Промокод",
        on_delete=models.SET_NULL,
        related_name="orders",
        blank=True,
        null=True,
    )
    discount_amount = models.DecimalField(
        "Скидка",
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

    @property
    def shop_settings(self):
        return ShopSettings.load()

    @property
    def return_period_days(self):
        return self.shop_settings.return_period_days

    @property
    def return_deadline(self):
        return self.created_at + timezone.timedelta(days=self.return_period_days)

    @property
    def return_period_is_active(self):
        return timezone.now() <= self.return_deadline

    @property
    def return_deadline_label(self):
        return timezone.localtime(self.return_deadline).strftime("%d.%m.%Y %H:%M")

    @property
    def active_reservation_deadline(self):
        active_reservations = self.reservations.filter(status=StockReservation.Status.ACTIVE)
        deadlines = [reservation.expires_at for reservation in active_reservations if reservation.expires_at]
        if not deadlines:
            return None
        return min(deadlines)

    @property
    def active_reservation_deadline_label(self):
        deadline = self.active_reservation_deadline
        if not deadline:
            return ""
        return timezone.localtime(deadline).strftime("%d.%m.%Y %H:%M")

    @property
    def has_active_reservations(self):
        return self.reservations.filter(status=StockReservation.Status.ACTIVE).exists()

    def recalculate_total(self):
        items_total = sum(item.subtotal for item in self.items.all())
        discount = self.discount_amount or Decimal("0.00")
        items_after_discount = max(items_total - discount, Decimal("0.00"))
        self.total_amount = items_after_discount + (self.delivery_price or Decimal("0.00"))
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

    @property
    def has_return_request(self):
        return hasattr(self, "return_request")

    @property
    def can_create_return_by_status(self):
        allowed_order_statuses = {"paid", "processing", "assembled", "shipped", "delivered"}
        return self.order.payment_status == "paid" and self.order.status in allowed_order_statuses

    @property
    def return_period_expired(self):
        return self.can_create_return_by_status and not self.order.return_period_is_active

    @property
    def can_create_return(self):
        return (
            not self.has_return_request
            and self.can_create_return_by_status
            and self.order.return_period_is_active
        )

    def __str__(self):
        return f"{self.product_variant} × {self.quantity}"


class StockReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Зарезервирован"
        CONFIRMED = "confirmed", "Подтверждён"
        RELEASED = "released", "Освобождён"

    order = models.ForeignKey(
        Order,
        verbose_name="Заказ",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    order_item = models.OneToOneField(
        OrderItem,
        verbose_name="Позиция заказа",
        on_delete=models.CASCADE,
        related_name="reservation",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Покупатель",
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        verbose_name="Вариант товара",
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    quantity = models.PositiveIntegerField(
        "Количество",
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(
        "Статус резерва",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    expires_at = models.DateTimeField(
        "Действует до",
        blank=True,
        null=True,
        db_index=True,
        help_text="Для онлайн-оплаты: время, после которого резерв автоматически освобождается.",
    )
    confirmed_at = models.DateTimeField(
        "Подтверждён",
        blank=True,
        null=True,
    )
    released_at = models.DateTimeField(
        "Освобождён",
        blank=True,
        null=True,
    )
    release_reason = models.CharField(
        "Причина освобождения",
        max_length=100,
        blank=True,
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
        verbose_name = "Резерв товара"
        verbose_name_plural = "Резервы товаров"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["product_variant", "status"]),
            models.Index(fields=["order", "status"]),
        ]

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    @property
    def deadline_label(self):
        if not self.expires_at:
            return ""
        return timezone.localtime(self.expires_at).strftime("%d.%m.%Y %H:%M")

    def __str__(self):
        return f"Резерв {self.product_variant} × {self.quantity} для {self.order.order_number}"


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
    photo = models.ImageField(
        "Фото товара",
        upload_to="returns/",
        blank=True,
        null=True,
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