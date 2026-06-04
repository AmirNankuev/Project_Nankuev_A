from django.db import transaction
from django.db.models import Sum

from main.models import CartItem
from main.services.reservations import get_available_quantity, release_expired_reservations
from .models import ProductVariant


CART_SESSION_KEY = "cart"
MAX_CART_ITEM_QUANTITY = 99


def normalize_cart_quantity(value, default=1):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        quantity = default

    return max(1, min(quantity, MAX_CART_ITEM_QUANTITY))


def get_session_cart(request):
    cart = request.session.get(CART_SESSION_KEY) if hasattr(request, "session") else None

    if not isinstance(cart, dict):
        cart = {}
        if hasattr(request, "session"):
            request.session[CART_SESSION_KEY] = cart

    return cart


def session_cart_items(cart):
    if not isinstance(cart, dict):
        return []

    items = []
    for key, value in cart.items():
        try:
            variant_id = int(key)
        except (TypeError, ValueError):
            continue

        quantity = normalize_cart_quantity(
            value.get("quantity", 1) if isinstance(value, dict) else value,
        )
        items.append((variant_id, quantity))

    return items


def is_db_cart_available(user):
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "is_customer_role", False)
        and not getattr(user, "can_manage_shop", False)
    )


def merge_session_cart_to_db(request, user=None):
    user = user or getattr(request, "user", None)

    if not is_db_cart_available(user):
        return 0

    release_expired_reservations()

    cart = get_session_cart(request)
    parsed_items = session_cart_items(cart)
    if not parsed_items:
        return 0

    valid_variant_ids = set(
        ProductVariant.objects.filter(
            pk__in=[variant_id for variant_id, _quantity in parsed_items],
            product__is_active=True,
        ).values_list("id", flat=True)
    )

    merged_count = 0
    with transaction.atomic():
        for variant_id, quantity in parsed_items:
            if variant_id not in valid_variant_ids:
                continue

            variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
            available_quantity = get_available_quantity(variant)
            quantity = min(quantity, available_quantity, MAX_CART_ITEM_QUANTITY)
            if quantity <= 0:
                continue

            cart_item, created = CartItem.objects.select_for_update().get_or_create(
                customer=user,
                product_variant=variant,
                defaults={"quantity": quantity},
            )

            if not created:
                cart_item.quantity = min(
                    cart_item.quantity + quantity,
                    MAX_CART_ITEM_QUANTITY,
                    available_quantity,
                )
                cart_item.save(update_fields=["quantity"])

            merged_count += quantity

    request.session[CART_SESSION_KEY] = {}
    request.session.modified = True
    return merged_count


def clear_cart_storage(request):
    user = getattr(request, "user", None)

    if is_db_cart_available(user):
        CartItem.objects.filter(customer=user).delete()

    if hasattr(request, "session"):
        request.session[CART_SESSION_KEY] = {}
        request.session.modified = True


def get_cart_count(request):
    user = getattr(request, "user", None)

    if is_db_cart_available(user):
        release_expired_reservations()
        merge_session_cart_to_db(request, user=user)
        total = CartItem.objects.filter(customer=user).aggregate(total=Sum("quantity"))["total"]
        return total or 0

    return sum(quantity for _variant_id, quantity in session_cart_items(get_session_cart(request)))
