from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from catalog.models import ProductVariant
from main.models import Order, OrderItem, ShopSettings, StockReservation


DEFAULT_RESERVATION_HOLD_MINUTES = 30
RESERVATION_RELEASE_EXPIRED = "expired"
RESERVATION_RELEASE_PAYMENT_FAILED = "payment_failed"
RESERVATION_RELEASE_CANCELLED = "cancelled"


class ReservationError(ValueError):
    """Ошибка резервирования товара."""


def get_reservation_hold_minutes():
    configured = getattr(settings, "RESERVATION_HOLD_MINUTES", None)
    if configured is not None:
        try:
            return max(1, int(configured))
        except (TypeError, ValueError):
            return DEFAULT_RESERVATION_HOLD_MINUTES

    try:
        return ShopSettings.load().reservation_hold_minutes
    except Exception:
        return DEFAULT_RESERVATION_HOLD_MINUTES


def get_reservation_expires_at(now=None):
    now = now or timezone.now()
    return now + timezone.timedelta(minutes=get_reservation_hold_minutes())


def _countable_active_filter(now=None):
    now = now or timezone.now()
    return Q(status=StockReservation.Status.ACTIVE) & (Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def release_expired_reservations(now=None):
    """
    Освобождает истёкшие резервы и отменяет неоплаченные заказы без активного резерва.

    Функция вызывается «лениво» на страницах каталога/корзины/оплаты и может быть
    запущена по расписанию через management command release_expired_reservations.
    """
    now = now or timezone.now()

    with transaction.atomic():
        expired_reservations = StockReservation.objects.select_for_update().filter(
            status=StockReservation.Status.ACTIVE,
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        # PostgreSQL не поддерживает SELECT ... FOR UPDATE вместе с DISTINCT.
        # Поэтому берём id заказов из уже заблокированной выборки и убираем дубли в Python.
        order_ids = list({
            order_id
            for order_id in expired_reservations.values_list("order_id", flat=True)
            if order_id
        })
        updated_count = expired_reservations.update(
            status=StockReservation.Status.RELEASED,
            released_at=now,
            release_reason=RESERVATION_RELEASE_EXPIRED,
            updated_at=now,
        )

        if order_ids:
            orders = Order.objects.select_for_update().filter(
                pk__in=order_ids,
                payment_status="pending",
            ).exclude(status__in=("paid", "processing", "assembled", "shipped", "delivered", "returned"))

            for order in orders:
                if not order.reservations.filter(status=StockReservation.Status.ACTIVE).exists():
                    old_status = order.status
                    old_payment_status = order.payment_status
                    order.status = "cancelled"
                    order.payment_status = "failed"
                    order.save(update_fields=["status", "payment_status", "updated_at"])

    return updated_count


def get_active_reserved_quantities(variant_ids=None, now=None):
    now = now or timezone.now()
    queryset = StockReservation.objects.filter(_countable_active_filter(now))

    if variant_ids is not None:
        variant_ids = [variant_id for variant_id in variant_ids if variant_id]
        if not variant_ids:
            return {}
        queryset = queryset.filter(product_variant_id__in=variant_ids)

    rows = queryset.values("product_variant_id").annotate(total=Sum("quantity"))
    return {row["product_variant_id"]: row["total"] or 0 for row in rows}


def attach_available_quantities(variants, now=None):
    variants = list(variants)
    reserved_by_variant = get_active_reserved_quantities([variant.pk for variant in variants], now=now)

    for variant in variants:
        reserved_quantity = reserved_by_variant.get(variant.pk, 0)
        variant.reserved_quantity = reserved_quantity
        variant.available_quantity = max((variant.quantity or 0) - reserved_quantity, 0)

    return variants


def get_available_quantity(variant, now=None):
    if hasattr(variant, "available_quantity"):
        return max(int(variant.available_quantity), 0)

    reserved_quantity = get_active_reserved_quantities([variant.pk], now=now).get(variant.pk, 0)
    return max((variant.quantity or 0) - reserved_quantity, 0)


def get_available_quantities_for_variants(variant_ids, now=None):
    variants = ProductVariant.objects.filter(pk__in=variant_ids)
    quantities = {variant.pk: variant.quantity or 0 for variant in variants}
    reserved = get_active_reserved_quantities(variant_ids, now=now)
    return {variant_id: max(quantities.get(variant_id, 0) - reserved.get(variant_id, 0), 0) for variant_id in variant_ids}


def create_order_items_and_reservations(order, cart_items, *, expires_at=None):
    """
    Создаёт позиции заказа и активные резервы без списания со склада.

    Склад уменьшается только после подтверждения оплаты через confirm_order_reservations().
    """
    release_expired_reservations()
    variant_ids = [item["variant"].pk for item in cart_items]
    reserved_by_variant = get_active_reserved_quantities(variant_ids)

    locked_variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
    }

    created_items = []
    for item in cart_items:
        variant = locked_variants.get(item["variant"].pk)
        if variant is None:
            raise ReservationError("Один из товаров больше недоступен для заказа.")

        quantity = int(item["quantity"])
        available_quantity = max((variant.quantity or 0) - reserved_by_variant.get(variant.pk, 0), 0)
        if available_quantity < quantity:
            raise ReservationError(f"Недостаточно свободного остатка: {variant}. Доступно: {available_quantity} шт.")

        order_item = OrderItem.objects.create(
            order=order,
            product_variant=variant,
            quantity=quantity,
            unit_price=item["price"],
        )
        StockReservation.objects.create(
            order=order,
            order_item=order_item,
            customer=order.customer,
            product_variant=variant,
            quantity=quantity,
            status=StockReservation.Status.ACTIVE,
            expires_at=expires_at,
        )
        reserved_by_variant[variant.pk] = reserved_by_variant.get(variant.pk, 0) + quantity
        created_items.append(order_item)

    return created_items


def confirm_order_reservations(order):
    """Подтверждает резервы оплаченного заказа и списывает товар со склада."""
    now = timezone.now()

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        reservations = list(
            StockReservation.objects
            .select_for_update()
            .filter(order=locked_order, status=StockReservation.Status.ACTIVE)
            .select_related("product_variant")
        )

        if not reservations:
            has_confirmed_reservations = locked_order.reservations.filter(
                status=StockReservation.Status.CONFIRMED,
            ).exists()
            has_any_reservations = locked_order.reservations.exists()

            if has_any_reservations and not has_confirmed_reservations:
                raise ReservationError("Активный резерв по заказу отсутствует: срок оплаты истёк или резерв был освобождён.")

            return 0

        quantities_by_variant = defaultdict(int)
        for reservation in reservations:
            quantities_by_variant[reservation.product_variant_id] += reservation.quantity

        if quantities_by_variant:
            variants = {
                variant.pk: variant
                for variant in ProductVariant.objects.select_for_update().filter(pk__in=quantities_by_variant.keys())
            }

            for variant_id, quantity in quantities_by_variant.items():
                variant = variants[variant_id]
                if variant.quantity < quantity:
                    raise ReservationError(f"Недостаточно товара для списания: {variant}")
                variant.quantity -= quantity
                variant.save(update_fields=["quantity"])

            StockReservation.objects.filter(pk__in=[reservation.pk for reservation in reservations]).update(
                status=StockReservation.Status.CONFIRMED,
                confirmed_at=now,
                updated_at=now,
            )

    return len(reservations)


def release_order_reservations(order, reason=RESERVATION_RELEASE_CANCELLED):
    """Освобождает активные резервы заказа без списания товара со склада."""
    now = timezone.now()
    with transaction.atomic():
        reservations = StockReservation.objects.select_for_update().filter(
            order=order,
            status=StockReservation.Status.ACTIVE,
        )
        return reservations.update(
            status=StockReservation.Status.RELEASED,
            released_at=now,
            release_reason=reason,
            updated_at=now,
        )
