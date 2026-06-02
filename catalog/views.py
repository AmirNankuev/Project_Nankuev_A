from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect

from main.models import Order, OrderItem
from main.services.cdek import CdekApiError, CdekClient
from main.services.yookassa_payment import (
    YooKassaApiError,
    YooKassaClient,
    payment_is_failed,
    payment_is_successful,
)

from .models import Product, Category, Brand, Color, ProductVariant, ProductImage


SORT_OPTIONS = [
    ("newest", "Сначала новые"),
    ("price_asc", "Цена: по возрастанию"),
    ("price_desc", "Цена: по убыванию"),
    ("name_asc", "Название: А–Я"),
]

VIEW_MODES = {"grid", "list"}


def _to_decimal(value):
    if not value:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError):
        return None


def _format_price(value):
    if value is None:
        return "Цена по запросу"
    return f"{value.quantize(Decimal('0.01'))} ₽"


def _get_matching_variants(product, color_id="", size=""):
    variants = list(getattr(product, "prepared_variants", product.variants.select_related("color").all()))

    if color_id:
        variants = [variant for variant in variants if str(variant.color_id) == str(color_id)]

    if size:
        variants = [variant for variant in variants if variant.size == size]

    return variants


def _prepare_catalog_product(product, color_id="", size=""):
    matching_variants = _get_matching_variants(product, color_id=color_id, size=size)
    prices = [variant.final_price for variant in matching_variants if variant.final_price and variant.final_price > Decimal("0.00")]
    in_stock = any(variant.quantity > 0 for variant in matching_variants)

    if prices:
        price_value = min(prices)
        price_prefix = "от " if len(set(prices)) > 1 else ""
        product.card_price_value = price_value
        product.card_price_label = f"{price_prefix}{_format_price(price_value)}"
    else:
        product.card_price_value = None
        product.card_price_label = "Цена по запросу"

    product.card_in_stock = in_stock
    product.card_matching_variants = matching_variants
    return product


def _apply_price_range(products, min_price_value=None, max_price_value=None):
    if min_price_value is None and max_price_value is None:
        return products

    filtered_products = []
    for product in products:
        price = product.card_price_value
        if price is None:
            continue
        if min_price_value is not None and price < min_price_value:
            continue
        if max_price_value is not None and price > max_price_value:
            continue
        filtered_products.append(product)
    return filtered_products


def _get_category_and_descendant_ids(category):
    category_ids = [category.id]

    for child in category.children.all():
        category_ids.extend(_get_category_and_descendant_ids(child))

    return category_ids


def _sort_products(products, sort_value):
    if sort_value == "price_asc":
        products.sort(key=lambda product: (product.card_price_value is None, product.card_price_value or Decimal("0.00")))
    elif sort_value == "price_desc":
        products.sort(key=lambda product: (product.card_price_value is None, -(product.card_price_value or Decimal("0.00"))))
    elif sort_value == "name_asc":
        products.sort(key=lambda product: product.name.lower())
    else:
        products.sort(key=lambda product: product.created_at, reverse=True)
    return products


def product_list(request):
    search_query = request.GET.get("search", "").strip()
    gender = request.GET.get("gender", "")
    category_id = request.GET.get("category", "")
    brand_id = request.GET.get("brand", "")
    color_id = request.GET.get("color", "")
    size = request.GET.get("size", "")

    if category_id and not category_id.isdigit():
        category_id = ""
    if brand_id and not brand_id.isdigit():
        brand_id = ""
    if color_id and not color_id.isdigit():
        color_id = ""
    availability = request.GET.get("availability", "")
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    sort_value = request.GET.get("sort", "newest")
    view_mode = request.GET.get("view", "grid")

    if gender not in dict(Category.Gender.choices):
        gender = ""

    if sort_value not in dict(SORT_OPTIONS):
        sort_value = "newest"

    if view_mode not in VIEW_MODES:
        view_mode = "grid"

    products_queryset = Product.objects.filter(
        is_active=True
    ).select_related(
        "brand",
        "category"
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
            to_attr="main_images"
        ),
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("color").order_by("color__name", "size"),
            to_attr="prepared_variants"
        )
    )

    if search_query:
        products_queryset = products_queryset.filter(
            Q(name__icontains=search_query)
            | Q(article__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(brand__name__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    if gender:
        products_queryset = products_queryset.filter(category__gender=gender)

    selected_category_object = None
    selected_category_ids = []

    if category_id:
        selected_category_object = (
            Category.objects
            .prefetch_related("children__children__children")
            .filter(pk=category_id)
            .first()
        )

        if selected_category_object:
            selected_category_ids = _get_category_and_descendant_ids(selected_category_object)
            products_queryset = products_queryset.filter(category_id__in=selected_category_ids)
        else:
            category_id = ""

    if brand_id:
        products_queryset = products_queryset.filter(brand_id=brand_id)

    variant_filter = {}
    if color_id:
        variant_filter["variants__color_id"] = color_id
    if size:
        variant_filter["variants__size"] = size
    if variant_filter:
        products_queryset = products_queryset.filter(**variant_filter)

    products_queryset = products_queryset.distinct()

    products_without_availability = [
        _prepare_catalog_product(product, color_id=color_id, size=size)
        for product in products_queryset
    ]

    min_price_value = _to_decimal(min_price)
    max_price_value = _to_decimal(max_price)
    products_without_availability = _apply_price_range(
        products_without_availability,
        min_price_value=min_price_value,
        max_price_value=max_price_value,
    )

    available_count = sum(1 for product in products_without_availability if product.card_in_stock)
    out_of_stock_count = sum(1 for product in products_without_availability if not product.card_in_stock)

    if availability == "in_stock":
        products = [product for product in products_without_availability if product.card_in_stock]
    elif availability == "out_of_stock":
        products = [product for product in products_without_availability if not product.card_in_stock]
    else:
        products = products_without_availability

    products = _sort_products(products, sort_value)

    def build_url(**updates):
        query_params = request.GET.copy()
        query_params.pop("page", None)

        for key, value in updates.items():
            if value in (None, ""):
                query_params.pop(key, None)
            else:
                query_params[key] = value

        encoded_query = query_params.urlencode()
        if encoded_query:
            return f"?{encoded_query}"
        return request.path

    categories_queryset = Category.objects.select_related("parent").order_by("name")
    if gender:
        categories_queryset = categories_queryset.filter(gender=gender)

    all_categories = list(categories_queryset)
    categories_by_parent = defaultdict(list)
    for category in all_categories:
        categories_by_parent[category.parent_id].append(category)

    category_options = []

    def add_category_options(parent_id=None, level=0):
        for category in sorted(categories_by_parent[parent_id], key=lambda item: item.name.lower()):
            category_id_str = str(category.id)
            is_active = category_id == category_id_str
            category_options.append({
                "object": category,
                "level": level,
                "padding": 9 + level * 16,
                "is_active": is_active,
                "url": build_url(category=None if is_active else category.id),
            })
            add_category_options(category.id, level + 1)

    add_category_options()

    size_options = []
    for size_item in ProductVariant.objects.values_list("size", flat=True).distinct().order_by("size"):
        is_active = size == size_item
        size_options.append({
            "value": size_item,
            "is_active": is_active,
            "url": build_url(size=None if is_active else size_item),
        })

    brand_options = []
    for brand in Brand.objects.all():
        brand_id_str = str(brand.id)
        is_active = brand_id == brand_id_str
        brand_options.append({
            "object": brand,
            "is_active": is_active,
            "url": build_url(brand=None if is_active else brand.id),
        })

    color_options = []
    for color in Color.objects.all():
        color_id_str = str(color.id)
        is_active = color_id == color_id_str
        color_options.append({
            "object": color,
            "is_active": is_active,
            "url": build_url(color=None if is_active else color.id),
        })

    sort_options = []
    for value, label in SORT_OPTIONS:
        sort_options.append({
            "value": value,
            "label": label,
            "is_active": sort_value == value,
        })

    paginator = Paginator(products, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(request, "pages/product_list.html", {
        "products": page_obj,
        "page_obj": page_obj,

        "search_query": search_query,
        "selected_gender": gender,
        "selected_category": category_id,
        "selected_category_object": selected_category_object,
        "selected_brand": brand_id,
        "selected_color": color_id,
        "selected_size": size,
        "selected_availability": availability,
        "min_price": min_price,
        "max_price": max_price,
        "selected_sort": sort_value,
        "view_mode": view_mode,

        "available_count": available_count,
        "out_of_stock_count": out_of_stock_count,
        "total_found": len(products),

        "categories": all_categories,
        "category_options": category_options,
        "brand_options": brand_options,
        "color_options": color_options,
        "size_options": size_options,
        "sort_options": sort_options,

        "all_url": build_url(category=None),
        "grid_view_url": build_url(view="grid"),
        "list_view_url": build_url(view="list"),
        "clear_availability_url": build_url(availability=None),
        "query_string": query_params.urlencode(),
    })


def _product_queryset():
    return Product.objects.filter(
        is_active=True
    ).select_related(
        "brand",
        "category"
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.order_by("-is_main", "sort_order", "id"),
            to_attr="gallery"
        ),
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("color").order_by("color__name", "size"),
            to_attr="prepared_variants"
        )
    )


def _product_detail_context(product):
    variants = list(getattr(product, "prepared_variants", product.variants.select_related("color").all()))

    color_options = []
    used_color_ids = set()
    for variant in variants:
        if variant.color_id in used_color_ids:
            continue
        used_color_ids.add(variant.color_id)
        color_options.append(variant.color)

    selected_variant = next((variant for variant in variants if variant.quantity > 0), variants[0] if variants else None)

    variant_options = []
    for variant in variants:
        variant_options.append({
            "id": variant.id,
            "size": variant.size,
            "color_name": variant.color.name,
            "color_hex": variant.color.hex_code,
            "price_label": variant.public_price_label,
            "quantity": variant.quantity,
            "is_selected": bool(selected_variant and variant.id == selected_variant.id),
        })

    selected_price_label = selected_variant.public_price_label if selected_variant else product.price_from_label

    similar_products = Product.objects.filter(
        is_active=True,
        category=product.category
    ).exclude(
        pk=product.pk
    ).select_related(
        "brand",
        "category"
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
            to_attr="main_images"
        ),
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("color").order_by("color__name", "size"),
            to_attr="prepared_variants"
        )
    )[:4]

    return {
        "product": product,
        "color_options": color_options,
        "variant_options": variant_options,
        "selected_price_label": selected_price_label,
        "selected_variant": selected_variant,
        "similar_products": similar_products,
    }


def product_detail(request, slug):
    product = get_object_or_404(_product_queryset(), slug=slug)
    return render(request, "pages/product_detail.html", _product_detail_context(product))


def product_detail_by_pk(request, pk):
    product = get_object_or_404(_product_queryset(), pk=pk)
    return render(request, "pages/product_detail.html", _product_detail_context(product))


CART_SESSION_KEY = "cart"
CART_SHIPPING_PRICE = Decimal("0.00")


def _money_label(value):
    value = value or Decimal("0.00")
    return f"{value.quantize(Decimal('0.01'))} ₽"


def _get_cart(request):
    cart = request.session.get(CART_SESSION_KEY)
    if not isinstance(cart, dict):
        cart = {}
        request.session[CART_SESSION_KEY] = cart
    return cart


def _cart_variant_ids(cart):
    ids = []
    for key in cart.keys():
        try:
            ids.append(int(key))
        except (TypeError, ValueError):
            continue
    return ids


def _cart_context(request):
    cart = _get_cart(request)
    variant_ids = _cart_variant_ids(cart)

    variants = ProductVariant.objects.filter(
        pk__in=variant_ids,
    ).select_related(
        "product",
        "product__brand",
        "product__category",
        "color",
    ).prefetch_related(
        Prefetch(
            "product__images",
            queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
            to_attr="main_images",
        )
    )

    variants_by_id = {variant.id: variant for variant in variants}
    items = []
    subtotal = Decimal("0.00")
    total_quantity = 0

    for variant_id in variant_ids:
        variant = variants_by_id.get(variant_id)
        if not variant:
            cart.pop(str(variant_id), None)
            request.session.modified = True
            continue

        try:
            quantity = int(cart.get(str(variant_id), {}).get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1

        quantity = max(1, min(quantity, 99))
        price = variant.final_price or Decimal("0.00")
        line_total = price * quantity
        subtotal += line_total
        total_quantity += quantity

        product = variant.product
        main_images = getattr(product, "main_images", [])
        image_url = main_images[0].image_url if main_images else ""

        items.append({
            "variant": variant,
            "product": product,
            "quantity": quantity,
            "price": price,
            "price_label": _money_label(price),
            "line_total": line_total,
            "line_total_label": _money_label(line_total),
            "image_url": image_url,
            "increase_quantity": quantity + 1,
            "decrease_quantity": quantity - 1,
        })

    shipping = CART_SHIPPING_PRICE if items else Decimal("0.00")
    total = subtotal + shipping

    return {
        "cart_items": items,
        "cart_count": total_quantity,
        "cart_subtotal": subtotal,
        "cart_subtotal_label": _money_label(subtotal),
        "cart_shipping": shipping,
        "cart_shipping_label": _money_label(shipping),
        "cart_total": total,
        "cart_total_label": _money_label(total),
    }


def cart_detail(request):
    return render(request, "pages/cart.html", _cart_context(request))


def _redirect_after_cart_action(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("cart")


def _add_variant_to_cart(request, variant):
    cart = _get_cart(request)
    key = str(variant.id)

    try:
        current_quantity = int(cart.get(key, {}).get("quantity", 0))
    except (TypeError, ValueError):
        current_quantity = 0

    cart[key] = {"quantity": max(1, min(current_quantity + 1, 99))}
    request.session.modified = True


def cart_add(request, variant_id):
    variant = get_object_or_404(
        ProductVariant.objects.select_related("product"),
        pk=variant_id,
        product__is_active=True,
    )
    _add_variant_to_cart(request, variant)
    return _redirect_after_cart_action(request)


def cart_add_product(request, product_id):
    product = get_object_or_404(Product.objects.filter(is_active=True), pk=product_id)
    variant = (
        ProductVariant.objects
        .filter(product=product, quantity__gt=0)
        .select_related("product")
        .order_by("color__name", "size")
        .first()
    )

    if variant is None:
        variant = (
            ProductVariant.objects
            .filter(product=product)
            .select_related("product")
            .order_by("color__name", "size")
            .first()
        )

    if variant is not None:
        _add_variant_to_cart(request, variant)

    return _redirect_after_cart_action(request)


def cart_update(request, variant_id):
    get_object_or_404(ProductVariant, pk=variant_id)
    cart = _get_cart(request)
    key = str(variant_id)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = {"quantity": min(quantity, 99)}

    request.session.modified = True
    return redirect("cart")


def cart_remove(request, variant_id):
    cart = _get_cart(request)
    cart.pop(str(variant_id), None)
    request.session.modified = True
    return redirect("cart")


CHECKOUT_SESSION_KEY = "checkout_customer_data"
CDEK_QUOTE_SESSION_KEY = "checkout_cdek_quote"
ONLINE_PAYMENT_METHODS = {"yookassa_card", "yookassa_sbp", "card_online", "sbp"}


def _build_delivery_address(data):
    country_labels = {
        "RU": "Россия",
        "KZ": "Казахстан",
        "BY": "Беларусь",
    }

    country = country_labels.get(data.get("country", ""), data.get("country", ""))
    address_parts = [
        f"Получатель: {data.get('last_name', '').strip()} {data.get('first_name', '').strip()}".strip(),
        f"Телефон: {data.get('phone', '').strip()}",
        f"Эл. почта: {data.get('email', '').strip()}",
        f"Страна: {country}",
        f"Регион: {data.get('region', '').strip()}",
        f"Город: {data.get('city', '').strip()}",
        f"Адрес: {data.get('address', '').strip()}",
        f"Индекс: {data.get('postal_code', '').strip()}",
    ]

    return "\n".join(part for part in address_parts if part and not part.endswith(":"))


def _cart_weight(cart_items):
    quantity = sum(item["quantity"] for item in cart_items)
    return max(quantity, 1) * settings.CDEK_DEFAULT_WEIGHT_GRAMS


def _delivery_recipient(data):
    full_name = f"{data.get('last_name', '').strip()} {data.get('first_name', '').strip()}".strip()
    return {
        "name": full_name or "Покупатель",
        "phone": data.get("phone", "").strip(),
        "email": data.get("email", "").strip(),
        "address": data.get("address", "").strip(),
    }


def _extract_cdek_uuid(cdek_payload):
    entity = cdek_payload.get("entity") if isinstance(cdek_payload, dict) else None
    if isinstance(entity, dict):
        return entity.get("uuid")
    return None


def _payment_requires_yookassa(payment_method):
    return payment_method in ONLINE_PAYMENT_METHODS


def _update_order_from_yookassa_payment(order, payment_payload):
    status = payment_payload.get("status") or "pending"
    fields_to_update = [
        "payment_status",
        "yookassa_payment_status",
        "yookassa_response",
        "updated_at",
    ]

    order.yookassa_payment_status = status
    order.yookassa_response = payment_payload.get("raw", payment_payload)

    if payment_is_successful(payment_payload):
        order.payment_status = "paid"
        order.status = "paid"
        fields_to_update.append("status")
    elif payment_is_failed(payment_payload):
        order.payment_status = "failed"

    order.save(update_fields=fields_to_update)
    return order


def _post_data_to_checkout_session(post_data):
    allowed_fields = (
        "email",
        "phone",
        "first_name",
        "last_name",
        "country",
        "region",
        "city",
        "address",
        "postal_code",
    )
    return {field: post_data.get(field, "").strip() for field in allowed_fields}


def _checkout_data_is_complete(data):
    required_fields = (
        "email",
        "phone",
        "first_name",
        "last_name",
        "country",
        "region",
        "city",
        "address",
        "postal_code",
    )
    return all(data.get(field) for field in required_fields)


def _clear_cdek_quote(request):
    request.session.pop(CDEK_QUOTE_SESSION_KEY, None)
    request.session.modified = True


def _quote_to_session_payload(delivery_info, delivery_type, cdek_city_code):
    return {
        "delivery_type": delivery_type,
        "cdek_city_code": str(cdek_city_code),
        "delivery_sum": str(delivery_info["delivery_sum"]),
        "period_min": delivery_info.get("period_min"),
        "period_max": delivery_info.get("period_max"),
        "tariff_code": delivery_info.get("tariff_code"),
    }


def _quote_from_session(payload):
    if not isinstance(payload, dict):
        return None

    delivery_sum = _to_decimal(payload.get("delivery_sum"))
    if delivery_sum is None:
        return None

    return {
        "delivery_type": payload.get("delivery_type") or "cdek_courier",
        "cdek_city_code": payload.get("cdek_city_code") or "",
        "delivery_sum": delivery_sum,
        "period_min": payload.get("period_min"),
        "period_max": payload.get("period_max"),
        "tariff_code": payload.get("tariff_code"),
    }


def _delivery_input_from_request_or_session(request):
    quote = _quote_from_session(request.session.get(CDEK_QUOTE_SESSION_KEY))
    return {
        "delivery_type": request.POST.get("delivery_type") or (quote or {}).get("delivery_type") or "cdek_courier",
        "cdek_city_code": request.POST.get("cdek_city_code") or (quote or {}).get("cdek_city_code") or "",
        "payment_method": request.POST.get("payment_method") or "yookassa_card",
    }


def _calculate_cdek_delivery(cart_context, delivery_type, cdek_city_code):
    if not cdek_city_code:
        raise ValueError("Укажите код города СДЭК.")

    try:
        city_code = int(cdek_city_code)
    except (TypeError, ValueError):
        raise ValueError("Код города СДЭК должен быть числом.")

    cdek = CdekClient()
    return cdek.calculate_tariff(
        to_city_code=city_code,
        delivery_type=delivery_type,
        weight=_cart_weight(cart_context["cart_items"]),
    )


def _delivery_page_context(request, cart_context, *, order=None, quote=None, delivery_input=None):
    context = dict(cart_context)
    quote = quote or _quote_from_session(request.session.get(CDEK_QUOTE_SESSION_KEY))
    delivery_input = delivery_input or _delivery_input_from_request_or_session(request)

    if quote:
        shipping = quote["delivery_sum"]
        total = context["cart_subtotal"] + shipping
        context.update({
            "cart_shipping": shipping,
            "cart_shipping_label": _money_label(shipping),
            "cart_total": total,
            "cart_total_label": _money_label(total),
            "cdek_quote": quote,
        })

    context.update({
        "checkout_data": request.session.get(CHECKOUT_SESSION_KEY, {}),
        "delivery_input": delivery_input,
        "cdek_demo_mode": settings.CDEK_DEMO_MODE,
        "yookassa_demo_mode": settings.YOOKASSA_DEMO_MODE,
        "order_submitted": bool(order),
        "created_order": order,
    })
    return context


def _create_order_from_cart(request, cart_context, delivery_info, checkout_data, delivery_type, payment_method):
    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user,
            delivery_address=_build_delivery_address(checkout_data),
            delivery_type=delivery_type,
            payment_method=payment_method or "yookassa_card",
            payment_status="pending",
            delivery_price=delivery_info["delivery_sum"],
            cdek_city_code=checkout_data.get("cdek_city_code") or None,
            cdek_tariff_code=delivery_info.get("tariff_code"),
            cdek_delivery_period_min=delivery_info.get("period_min"),
            cdek_delivery_period_max=delivery_info.get("period_max"),
        )

        for item in cart_context["cart_items"]:
            variant = ProductVariant.objects.select_for_update().get(pk=item["variant"].pk)
            quantity = item["quantity"]

            if variant.quantity < quantity:
                raise ValueError(f"Недостаточно товара на складе: {variant}")

            variant.quantity -= quantity
            variant.save(update_fields=["quantity"])

            OrderItem.objects.create(
                order=order,
                product_variant=variant,
                quantity=quantity,
                unit_price=item["price"],
            )

        order.recalculate_total()

    return order


@login_required
def checkout(request):
    context = _cart_context(request)
    checkout_data = request.session.get(CHECKOUT_SESSION_KEY, {})
    context["checkout_data"] = checkout_data

    if request.method == "POST":
        if not context["cart_items"]:
            messages.error(request, "Нельзя оформить пустую корзину.")
            return redirect("cart")

        checkout_data = _post_data_to_checkout_session(request.POST)
        if not _checkout_data_is_complete(checkout_data):
            messages.error(request, "Заполните контактные данные и адрес доставки.")
            context["checkout_data"] = checkout_data
            return render(request, "pages/checkout.html", context)

        request.session[CHECKOUT_SESSION_KEY] = checkout_data
        _clear_cdek_quote(request)
        return redirect("checkout_delivery")

    return render(request, "pages/checkout.html", context)


@login_required
def checkout_delivery(request):
    cart_context = _cart_context(request)
    checkout_data = request.session.get(CHECKOUT_SESSION_KEY, {})

    if not cart_context["cart_items"]:
        messages.error(request, "Нельзя оформить пустую корзину.")
        return redirect("cart")

    if not _checkout_data_is_complete(checkout_data):
        messages.error(request, "Сначала заполните контактные данные и адрес доставки.")
        return redirect("checkout")

    delivery_input = _delivery_input_from_request_or_session(request)

    if request.method == "POST":
        action = request.POST.get("action") or "calculate"
        delivery_type = delivery_input["delivery_type"]
        cdek_city_code = delivery_input["cdek_city_code"]

        try:
            delivery_info = _calculate_cdek_delivery(cart_context, delivery_type, cdek_city_code)
        except ValueError as error:
            messages.error(request, str(error))
            return render(
                request,
                "pages/checkout_delivery.html",
                _delivery_page_context(request, cart_context, delivery_input=delivery_input),
            )
        except CdekApiError as error:
            messages.error(request, f"СДЭК не рассчитал доставку: {error}")
            return render(
                request,
                "pages/checkout_delivery.html",
                _delivery_page_context(request, cart_context, delivery_input=delivery_input),
            )

        quote = {
            "delivery_type": delivery_type,
            "cdek_city_code": str(cdek_city_code),
            "delivery_sum": delivery_info["delivery_sum"],
            "period_min": delivery_info.get("period_min"),
            "period_max": delivery_info.get("period_max"),
            "tariff_code": delivery_info.get("tariff_code"),
        }
        request.session[CDEK_QUOTE_SESSION_KEY] = _quote_to_session_payload(delivery_info, delivery_type, cdek_city_code)
        request.session.modified = True

        if action == "calculate":
            messages.success(request, "Доставка СДЭК рассчитана. Проверьте сумму и подтвердите заказ.")
            return render(
                request,
                "pages/checkout_delivery.html",
                _delivery_page_context(request, cart_context, quote=quote, delivery_input=delivery_input),
            )

        try:
            order = _create_order_from_cart(
                request,
                cart_context,
                delivery_info,
                {**checkout_data, "cdek_city_code": cdek_city_code},
                delivery_type,
                delivery_input["payment_method"],
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("cart")

        cdek = CdekClient()
        try:
            cdek_response = cdek.create_order(
                order=order,
                recipient=_delivery_recipient(checkout_data),
                to_city_code=int(cdek_city_code),
                delivery_type=delivery_type,
                weight=_cart_weight(cart_context["cart_items"]),
                tariff_code=delivery_info.get("tariff_code"),
            )
            order.cdek_uuid = _extract_cdek_uuid(cdek_response)
            order.cdek_status = "demo" if settings.CDEK_DEMO_MODE else "created"
            order.cdek_response = cdek_response
            order.cdek_error = ""
            order.save(update_fields=["cdek_uuid", "cdek_status", "cdek_response", "cdek_error"])
        except CdekApiError as error:
            order.cdek_status = "error"
            order.cdek_error = str(error)
            order.save(update_fields=["cdek_status", "cdek_error"])
            messages.warning(request, "Заказ создан локально, но не был отправлен в СДЭК. Проверьте заказ в админке.")

        request.session[CART_SESSION_KEY] = {}
        request.session.pop(CHECKOUT_SESSION_KEY, None)
        request.session.pop(CDEK_QUOTE_SESSION_KEY, None)
        request.session.modified = True

        if _payment_requires_yookassa(delivery_input["payment_method"]):
            yookassa = YooKassaClient(request)
            try:
                payment_payload = yookassa.create_payment(order)
                order.yookassa_payment_id = payment_payload.get("id")
                order.yookassa_payment_status = payment_payload.get("status") or "pending"
                order.yookassa_confirmation_url = payment_payload.get("confirmation_url") or ""
                order.yookassa_response = payment_payload.get("raw")
                order.yookassa_error = ""
                order.save(update_fields=[
                    "yookassa_payment_id",
                    "yookassa_payment_status",
                    "yookassa_confirmation_url",
                    "yookassa_response",
                    "yookassa_error",
                ])

                if order.yookassa_confirmation_url:
                    return redirect(order.yookassa_confirmation_url)

                return redirect("checkout_payment", order_number=order.order_number)
            except YooKassaApiError as error:
                order.yookassa_payment_status = "error"
                order.yookassa_error = str(error)
                order.save(update_fields=["yookassa_payment_status", "yookassa_error"])
                messages.warning(request, "Заказ создан, но платёж ЮKassa не был сформирован. Проверьте настройки оплаты.")
                return redirect("checkout_payment", order_number=order.order_number)

        order_items_total = sum(item.subtotal for item in order.items.all())
        order_items_count = sum(item.quantity for item in order.items.all())
        success_context = _delivery_page_context(request, cart_context, order=order, quote=quote, delivery_input=delivery_input)
        success_context.update({
            "cart_count": order_items_count,
            "cart_subtotal": order_items_total,
            "cart_subtotal_label": _money_label(order_items_total),
            "cart_shipping": order.delivery_price,
            "cart_shipping_label": _money_label(order.delivery_price),
            "cart_total": order.total_amount,
            "cart_total_label": _money_label(order.total_amount),
        })
        return render(request, "pages/checkout_delivery.html", success_context)

    return render(
        request,
        "pages/checkout_delivery.html",
        _delivery_page_context(request, cart_context, delivery_input=delivery_input),
    )



@login_required
def checkout_payment(request, order_number):
    orders = Order.objects.prefetch_related(
        "items__product_variant__product",
        "items__product_variant__color",
    )

    if not request.user.is_staff:
        orders = orders.filter(customer=request.user)

    order = get_object_or_404(orders, order_number=order_number)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "demo_success":
            if not settings.YOOKASSA_DEMO_MODE:
                messages.error(request, "Демо-оплата отключена. Проверьте платёж через ЮKassa.")
                return redirect("checkout_payment", order_number=order.order_number)

            demo_payload = {
                "id": order.yookassa_payment_id or f"demo_{order.order_number.lower()}",
                "status": "succeeded",
                "paid": True,
                "demo": True,
            }
            _update_order_from_yookassa_payment(order, demo_payload)
            messages.success(request, "Тестовая оплата выполнена. Заказ переведён в статус «Оплачен».")
            return redirect("checkout_payment", order_number=order.order_number)

        if action == "check":
            return redirect("checkout_payment", order_number=order.order_number)

    if order.yookassa_payment_id and order.payment_status != "paid" and not settings.YOOKASSA_DEMO_MODE:
        yookassa = YooKassaClient(request)
        try:
            payment_payload = yookassa.get_payment(order.yookassa_payment_id)
            _update_order_from_yookassa_payment(order, payment_payload)
        except YooKassaApiError as error:
            order.yookassa_error = str(error)
            order.save(update_fields=["yookassa_error"])
            messages.warning(request, f"Не удалось проверить статус платежа ЮKassa: {error}")

    order_items = list(order.items.all())
    items_total = sum(item.subtotal for item in order_items)

    return render(request, "pages/checkout_payment.html", {
        "order": order,
        "order_items": order_items,
        "items_total": items_total,
        "items_total_label": _money_label(items_total),
        "delivery_price_label": _money_label(order.delivery_price),
        "total_label": _money_label(order.total_amount),
        "yookassa_demo_mode": settings.YOOKASSA_DEMO_MODE,
        "can_demo_pay": settings.YOOKASSA_DEMO_MODE and order.payment_status != "paid",
    })
