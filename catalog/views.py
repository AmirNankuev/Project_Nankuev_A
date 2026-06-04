from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from main.forms import ReturnRequestForm
from main.email_notifications import (
    notify_order_created,
    notify_order_status_changed,
    notify_return_request_created,
)
from main.models import CartItem, Order, OrderItem, PromoCode, ReturnRequest, ShopSettings
from main.services.cdek import CdekApiError, CdekClient
from main.services.reservations import (
    ReservationError,
    attach_available_quantities,
    confirm_order_reservations,
    create_order_items_and_reservations,
    get_available_quantity,
    get_reservation_expires_at,
    release_expired_reservations,
    release_order_reservations,
    RESERVATION_RELEASE_PAYMENT_FAILED,
)
from users.decorators import customer_required

from main.services.yookassa_payment import (
    YooKassaApiError,
    YooKassaClient,
    payment_is_failed,
    payment_is_successful,
)

from .cart_services import (
    MAX_CART_ITEM_QUANTITY,
    clear_cart_storage,
    get_session_cart,
    is_db_cart_available,
    merge_session_cart_to_db,
    normalize_cart_quantity,
    session_cart_items,
)
from .forms import ProductReviewForm
from .models import Product, Category, Brand, Collection, Color, ProductVariant, ProductImage, ProductReview


SORT_OPTIONS = [
    ("newest", "Сначала новые"),
    ("price_asc", "Цена: по возрастанию"),
    ("price_desc", "Цена: по убыванию"),
    ("name_asc", "Название: А–Я"),
]

VIEW_MODES = {"grid", "list"}
REVIEW_ELIGIBLE_ORDER_STATUSES = {"paid", "processing", "assembled", "shipped", "delivered"}


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


def _with_review_stats(queryset):
    return queryset.annotate(
        published_reviews_count=Count(
            "reviews",
            filter=Q(reviews__status=ProductReview.Status.PUBLISHED),
            distinct=True,
        ),
        published_average_rating=Avg(
            "reviews__rating",
            filter=Q(reviews__status=ProductReview.Status.PUBLISHED),
        ),
    )


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
    in_stock = any(get_available_quantity(variant) > 0 for variant in matching_variants)

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


def _attach_product_variant_availability(products):
    variants = []
    for product in products:
        variants.extend(getattr(product, "prepared_variants", []))
    attach_available_quantities(variants)
    return products


def product_list(request):
    release_expired_reservations()
    search_query = request.GET.get("search", "").strip()
    gender = request.GET.get("gender", "")
    category_id = request.GET.get("category", "")
    collection_id = request.GET.get("collection", "")
    brand_id = request.GET.get("brand", "")
    color_id = request.GET.get("color", "")
    size = request.GET.get("size", "")

    if category_id and not category_id.isdigit():
        category_id = ""
    if collection_id and not collection_id.isdigit():
        collection_id = ""
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

    products_queryset = _with_review_stats(Product.objects.filter(
        is_active=True
    )).select_related(
        "brand",
        "category"
    ).prefetch_related(
        "collections",
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
            | Q(collections__name__icontains=search_query)
            | Q(collections__season__icontains=search_query)
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

    selected_collection_object = None

    if collection_id:
        selected_collection_object = Collection.objects.filter(pk=collection_id, is_active=True).first()
        if selected_collection_object:
            products_queryset = products_queryset.filter(collections=selected_collection_object)
        else:
            collection_id = ""

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

    products_queryset = list(products_queryset)
    _attach_product_variant_availability(products_queryset)

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

    collection_options = []
    for collection in Collection.objects.filter(is_active=True).order_by("sort_order", "-year", "name"):
        collection_id_str = str(collection.id)
        is_active = collection_id == collection_id_str
        collection_options.append({
            "object": collection,
            "is_active": is_active,
            "url": build_url(collection=None if is_active else collection.id),
        })

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
        "selected_collection": collection_id,
        "selected_collection_object": selected_collection_object,
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
        "collection_options": collection_options,
        "brand_options": brand_options,
        "color_options": color_options,
        "size_options": size_options,
        "sort_options": sort_options,

        "all_url": build_url(category=None),
        "grid_view_url": build_url(view="grid"),
        "list_view_url": build_url(view="list"),
        "clear_availability_url": build_url(availability=None),
        "clear_collection_url": build_url(collection=None),
        "query_string": query_params.urlencode(),
    })


def _product_queryset():
    return _with_review_stats(Product.objects.filter(
        is_active=True
    )).select_related(
        "brand",
        "category"
    ).prefetch_related(
        "collections",
        Prefetch(
            "images",
            queryset=ProductImage.objects.order_by("-is_main", "sort_order", "id"),
            to_attr="gallery"
        ),
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("color").order_by("color__name", "size"),
            to_attr="prepared_variants"
        ),
        Prefetch(
            "reviews",
            queryset=ProductReview.objects.filter(
                status=ProductReview.Status.PUBLISHED
            ).select_related("customer").order_by("-created_at"),
            to_attr="published_reviews",
        )
    )


def _get_review_order_item(product, user):
    if not user.is_authenticated or not getattr(user, "is_customer_role", False):
        return None

    return (
        OrderItem.objects
        .filter(
            order__customer=user,
            order__payment_status="paid",
            order__status__in=REVIEW_ELIGIBLE_ORDER_STATUSES,
            product_variant__product=product,
        )
        .select_related("order", "product_variant", "product_variant__product")
        .order_by("-order__created_at")
        .first()
    )


def _product_detail_context(product, request=None, review_form=None):
    variants = list(getattr(product, "prepared_variants", product.variants.select_related("color").all()))
    attach_available_quantities(variants)

    color_options = []
    used_color_ids = set()
    for variant in variants:
        if variant.color_id in used_color_ids:
            continue
        used_color_ids.add(variant.color_id)
        color_options.append(variant.color)

    selected_variant = next((variant for variant in variants if get_available_quantity(variant) > 0), None)

    variant_options = []
    for variant in variants:
        variant_options.append({
            "id": variant.id,
            "size": variant.size,
            "color_name": variant.color.name,
            "color_hex": variant.color.hex_code,
            "price_label": variant.public_price_label,
            "quantity": get_available_quantity(variant),
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
        "collections",
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

    reviews = getattr(product, "published_reviews", None)
    if reviews is None:
        reviews = list(ProductReview.objects.filter(
            product=product,
            status=ProductReview.Status.PUBLISHED,
        ).select_related("customer").order_by("-created_at"))

    existing_user_review = None
    review_order_item = None
    can_create_review = False

    if request and request.user.is_authenticated and getattr(request.user, "is_customer_role", False):
        existing_user_review = ProductReview.objects.filter(
            product=product,
            customer=request.user,
        ).first()
        review_order_item = _get_review_order_item(product, request.user)
        can_create_review = review_order_item is not None and existing_user_review is None

    return {
        "product": product,
        "color_options": color_options,
        "variant_options": variant_options,
        "selected_price_label": selected_price_label,
        "selected_variant": selected_variant,
        "similar_products": similar_products,
        "reviews": reviews,
        "review_form": review_form or ProductReviewForm(),
        "existing_user_review": existing_user_review,
        "review_order_item": review_order_item,
        "can_create_review": can_create_review,
    }


def product_detail(request, slug):
    release_expired_reservations()
    product = get_object_or_404(_product_queryset(), slug=slug)
    return render(request, "pages/product_detail.html", _product_detail_context(product, request=request))


def product_detail_by_pk(request, pk):
    release_expired_reservations()
    product = get_object_or_404(_product_queryset(), pk=pk)
    return render(request, "pages/product_detail.html", _product_detail_context(product, request=request))


def _redirect_to_product_reviews(product):
    return redirect(f"{reverse('catalog:product_detail', kwargs={'slug': product.slug})}#reviews")


@require_POST
@customer_required
def add_product_review(request, slug):
    release_expired_reservations()
    product = get_object_or_404(Product.objects.filter(is_active=True), slug=slug)
    review_order_item = _get_review_order_item(product, request.user)

    if review_order_item is None:
        messages.error(request, "Оставить отзыв можно после оплаты заказа с этим товаром.")
        return _redirect_to_product_reviews(product)

    if ProductReview.objects.filter(product=product, customer=request.user).exists():
        messages.info(request, "Вы уже оставили отзыв на этот товар.")
        return _redirect_to_product_reviews(product)

    form = ProductReviewForm(request.POST)
    if not form.is_valid():
        product = get_object_or_404(_product_queryset(), slug=slug)
        context = _product_detail_context(product, request=request, review_form=form)
        return render(request, "pages/product_detail.html", context, status=400)

    review = form.save(commit=False)
    review.product = product
    review.customer = request.user
    review.order_item = review_order_item
    review.status = ProductReview.Status.PUBLISHED
    review.save()

    messages.success(request, "Спасибо! Ваш отзыв опубликован.")
    return _redirect_to_product_reviews(product)


PROMO_SESSION_KEY = "promo_code"
CART_SHIPPING_PRICE = Decimal("0.00")


def _shop_settings():
    return ShopSettings.load()


def _free_delivery_threshold():
    settings_obj = _shop_settings()
    if settings_obj.free_delivery_enabled:
        return settings_obj.free_delivery_from
    return None


def _free_delivery_applies(cart_context, delivery_sum):
    threshold = _free_delivery_threshold()
    if not threshold:
        return False

    subtotal_after_discount = cart_context.get("cart_subtotal_after_discount", Decimal("0.00"))
    return delivery_sum > Decimal("0.00") and subtotal_after_discount >= threshold


def _apply_shop_delivery_rules(cart_context, delivery_info):
    delivery_info = dict(delivery_info)
    original_sum = delivery_info.get("delivery_sum") or Decimal("0.00")
    threshold = _free_delivery_threshold()

    delivery_info["original_delivery_sum"] = original_sum
    delivery_info["free_delivery_from"] = threshold
    delivery_info["free_delivery_applied"] = _free_delivery_applies(cart_context, original_sum)

    if delivery_info["free_delivery_applied"]:
        delivery_info["delivery_sum"] = Decimal("0.00")

    return delivery_info


def _money_label(value):
    value = value or Decimal("0.00")
    return f"{value.quantize(Decimal('0.01'))} ₽"


def _clear_promo(request):
    request.session.pop(PROMO_SESSION_KEY, None)
    request.session.modified = True


def _get_session_promo(request):
    code = request.session.get(PROMO_SESSION_KEY, "")
    if not code:
        return None

    try:
        return PromoCode.objects.get(code=str(code).strip().upper())
    except PromoCode.DoesNotExist:
        _clear_promo(request)
        return None


def _promo_context(request, subtotal):
    promo = _get_session_promo(request)
    discount = Decimal("0.00")
    promo_error = ""

    if promo is not None:
        promo_error = promo.get_unavailable_reason(subtotal)
        if promo_error:
            _clear_promo(request)
            promo = None
        else:
            discount = promo.calculate_discount(subtotal)

    return {
        "promo": promo,
        "promo_code": promo.code if promo else "",
        "promo_discount": discount,
        "promo_discount_label": _money_label(discount),
        "promo_error": promo_error,
    }


def _apply_promo(request, subtotal):
    raw_code = request.POST.get("promo_code", "")
    code = raw_code.strip().upper()

    if not code:
        messages.error(request, "Введите промокод.")
        return

    try:
        promo = PromoCode.objects.get(code=code)
    except PromoCode.DoesNotExist:
        messages.error(request, "Такого промокода нет.")
        return

    reason = promo.get_unavailable_reason(subtotal)
    if reason:
        messages.error(request, reason)
        return

    request.session[PROMO_SESSION_KEY] = promo.code
    request.session.modified = True
    messages.success(request, f"Промокод {promo.code} применён. Скидка: {_money_label(promo.calculate_discount(subtotal))}.")


def _handle_promo_action(request, subtotal):
    action = request.POST.get("action")

    if action == "apply_promo":
        _apply_promo(request, subtotal)
        return True

    if action == "remove_promo":
        _clear_promo(request)
        messages.info(request, "Промокод удалён.")
        return True

    return False


def _cart_variant_queryset(variant_ids):
    return ProductVariant.objects.filter(
        pk__in=variant_ids,
        product__is_active=True,
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


def _cart_item_queryset(user):
    return CartItem.objects.filter(
        customer=user,
    ).select_related(
        "product_variant",
        "product_variant__product",
        "product_variant__product__brand",
        "product_variant__product__category",
        "product_variant__color",
    ).prefetch_related(
        Prefetch(
            "product_variant__product__images",
            queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
            to_attr="main_images",
        )
    ).order_by("-added_at")


def _cart_item_payload(variant, quantity):
    available_quantity = get_available_quantity(variant)
    quantity = min(normalize_cart_quantity(quantity), available_quantity)
    price = variant.final_price or Decimal("0.00")
    line_total = price * quantity
    product = variant.product
    main_images = getattr(product, "main_images", [])
    image_url = main_images[0].image_url if main_images else ""

    return {
        "variant": variant,
        "product": product,
        "quantity": quantity,
        "available_quantity": available_quantity,
        "reserved_quantity": getattr(variant, "reserved_quantity", 0),
        "price": price,
        "price_label": _money_label(price),
        "line_total": line_total,
        "line_total_label": _money_label(line_total),
        "image_url": image_url,
        "increase_quantity": quantity + 1,
        "decrease_quantity": quantity - 1,
    }


def _database_cart_items(request):
    merge_session_cart_to_db(request)

    items = []
    cart_items = list(_cart_item_queryset(request.user))
    attach_available_quantities([cart_item.product_variant for cart_item in cart_items])

    for cart_item in cart_items:
        available_quantity = get_available_quantity(cart_item.product_variant)
        if available_quantity <= 0:
            cart_item.delete()
            continue

        quantity = min(normalize_cart_quantity(cart_item.quantity), available_quantity)
        if cart_item.quantity != quantity:
            cart_item.quantity = quantity
            cart_item.save(update_fields=["quantity"])

        items.append(_cart_item_payload(cart_item.product_variant, quantity))

    return items


def _session_cart_items(request):
    cart = get_session_cart(request)
    parsed_items = session_cart_items(cart)
    variant_ids = [variant_id for variant_id, _quantity in parsed_items]
    variants = list(_cart_variant_queryset(variant_ids))
    attach_available_quantities(variants)
    variants_by_id = {variant.id: variant for variant in variants}

    items = []
    cart_changed = False

    for variant_id, quantity in parsed_items:
        variant = variants_by_id.get(variant_id)
        if variant is None or get_available_quantity(variant) <= 0:
            cart.pop(str(variant_id), None)
            cart_changed = True
            continue

        normalized_quantity = min(normalize_cart_quantity(quantity), get_available_quantity(variant))
        if normalized_quantity != quantity:
            cart[str(variant_id)] = {"quantity": normalized_quantity}
            cart_changed = True

        items.append(_cart_item_payload(variant, normalized_quantity))

    if cart_changed:
        request.session.modified = True

    return items


def _cart_context(request):
    if is_db_cart_available(request.user):
        items = _database_cart_items(request)
    else:
        items = _session_cart_items(request)

    subtotal = Decimal("0.00")
    total_quantity = 0

    for item in items:
        subtotal += item["line_total"]
        total_quantity += item["quantity"]

    promo_data = _promo_context(request, subtotal) if items else {
        "promo": None,
        "promo_code": "",
        "promo_discount": Decimal("0.00"),
        "promo_discount_label": _money_label(Decimal("0.00")),
        "promo_error": "",
    }
    discount = promo_data["promo_discount"]
    shipping = CART_SHIPPING_PRICE if items else Decimal("0.00")
    subtotal_after_discount = max(subtotal - discount, Decimal("0.00"))
    total = subtotal_after_discount + shipping

    return {
        "cart_items": items,
        "cart_count": total_quantity,
        "cart_subtotal": subtotal,
        "cart_subtotal_label": _money_label(subtotal),
        "cart_subtotal_after_discount": subtotal_after_discount,
        "cart_subtotal_after_discount_label": _money_label(subtotal_after_discount),
        "cart_shipping": shipping,
        "cart_shipping_label": _money_label(shipping),
        "cart_total": total,
        "cart_total_label": _money_label(total),
        "shop_settings": _shop_settings(),
        "free_delivery_from": _free_delivery_threshold(),
        "free_delivery_from_label": _money_label(_free_delivery_threshold()) if _free_delivery_threshold() else "",
        **promo_data,
    }


def _customer_features_allowed(request):
    if request.user.is_authenticated and not getattr(request.user, "is_customer_role", False):
        messages.error(request, "Корзина и оформление заказа доступны только покупателю.")
        return False
    return True


def cart_detail(request):
    release_expired_reservations()
    if not _customer_features_allowed(request):
        return redirect("users:staff_dashboard")

    context = _cart_context(request)
    return render(request, "pages/cart.html", context)


def _redirect_after_cart_action(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("cart")


def _variant_can_be_added(request, variant):
    if get_available_quantity(variant) <= 0:
        messages.error(request, "Этот размер/цвет сейчас отсутствует на складе.")
        return False
    return True


def _add_variant_to_session_cart(request, variant):
    cart = get_session_cart(request)
    key = str(variant.id)

    current_quantity = 0
    if isinstance(cart.get(key), dict):
        current_quantity = normalize_cart_quantity(cart[key].get("quantity", 0), default=0)

    new_quantity = min(current_quantity + 1, MAX_CART_ITEM_QUANTITY, get_available_quantity(variant))
    cart[key] = {"quantity": new_quantity}
    request.session.modified = True


def _add_variant_to_database_cart(request, variant):
    merge_session_cart_to_db(request)

    with transaction.atomic():
        locked_variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        available_quantity = get_available_quantity(locked_variant)
        if available_quantity <= 0:
            messages.error(request, "Этот размер/цвет сейчас отсутствует на складе.")
            return

        cart_item, created = CartItem.objects.select_for_update().get_or_create(
            customer=request.user,
            product_variant=locked_variant,
            defaults={"quantity": 1},
        )

        if not created:
            cart_item.quantity = min(cart_item.quantity + 1, MAX_CART_ITEM_QUANTITY, available_quantity)
            cart_item.save(update_fields=["quantity"])


def _add_variant_to_cart(request, variant):
    if not _variant_can_be_added(request, variant):
        return

    if is_db_cart_available(request.user):
        _add_variant_to_database_cart(request, variant)
    else:
        _add_variant_to_session_cart(request, variant)


def cart_add(request, variant_id):
    if not _customer_features_allowed(request):
        return redirect("users:staff_dashboard")

    variant = get_object_or_404(
        ProductVariant.objects.select_related("product"),
        pk=variant_id,
        product__is_active=True,
    )
    _add_variant_to_cart(request, variant)
    return _redirect_after_cart_action(request)


def cart_add_product(request, product_id):
    if not _customer_features_allowed(request):
        return redirect("users:staff_dashboard")

    product = get_object_or_404(Product.objects.filter(is_active=True), pk=product_id)
    variants = list(
        ProductVariant.objects
        .filter(product=product)
        .select_related("product")
        .order_by("color__name", "size")
    )
    attach_available_quantities(variants)
    variant = next((item for item in variants if get_available_quantity(item) > 0), None)

    if variant is None:
        messages.error(request, "У этого товара нет доступных вариантов на складе.")
    else:
        _add_variant_to_cart(request, variant)

    return _redirect_after_cart_action(request)


def _quantity_from_request(request):
    try:
        return int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        return 1


def _limited_quantity_for_variant(request, variant, requested_quantity):
    if requested_quantity <= 0:
        return 0

    available_quantity = get_available_quantity(variant)
    if available_quantity <= 0:
        messages.error(request, "Этот товар закончился на складе и удалён из корзины.")
        return 0

    limited_quantity = min(requested_quantity, MAX_CART_ITEM_QUANTITY, available_quantity)
    if limited_quantity < requested_quantity:
        messages.warning(request, f"В наличии только {limited_quantity} шт. Количество в корзине уменьшено.")

    return limited_quantity


def cart_update(request, variant_id):
    if not _customer_features_allowed(request):
        return redirect("users:staff_dashboard")

    variant = get_object_or_404(ProductVariant, pk=variant_id)
    requested_quantity = _quantity_from_request(request)
    quantity = _limited_quantity_for_variant(request, variant, requested_quantity)

    if is_db_cart_available(request.user):
        merge_session_cart_to_db(request)
        cart_item = CartItem.objects.filter(customer=request.user, product_variant=variant).first()

        if cart_item is not None:
            if quantity <= 0:
                cart_item.delete()
            else:
                cart_item.quantity = quantity
                cart_item.save(update_fields=["quantity"])
    else:
        cart = get_session_cart(request)
        key = str(variant_id)
        if quantity <= 0:
            cart.pop(key, None)
        else:
            cart[key] = {"quantity": quantity}
        request.session.modified = True

    return redirect("cart")


def cart_remove(request, variant_id):
    if not _customer_features_allowed(request):
        return redirect("users:staff_dashboard")

    if is_db_cart_available(request.user):
        merge_session_cart_to_db(request)
        CartItem.objects.filter(customer=request.user, product_variant_id=variant_id).delete()
    else:
        cart = get_session_cart(request)
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
    old_status = order.status
    old_payment_status = order.payment_status

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
        if order.payment_status != "paid":
            try:
                confirmed_count = confirm_order_reservations(order)
            except ReservationError as error:
                confirmed_count = 0
                order.yookassa_error = str(error)
                fields_to_update.append("yookassa_error")

            if confirmed_count:
                order.payment_status = "paid"
                order.status = "paid"
                fields_to_update.append("status")
            else:
                order.payment_status = "failed"
                order.status = "cancelled"
                order.yookassa_error = "Резерв товара истёк или был освобождён. Заказ отменён в системе."
                fields_to_update.extend(["status", "yookassa_error"])
        else:
            order.status = "paid"
            fields_to_update.append("status")
    elif payment_is_failed(payment_payload):
        release_order_reservations(order, reason=RESERVATION_RELEASE_PAYMENT_FAILED)
        order.payment_status = "failed"
        order.status = "cancelled"
        fields_to_update.append("status")

    order.save(update_fields=list(dict.fromkeys(fields_to_update)))
    notify_order_status_changed(order, old_status=old_status, old_payment_status=old_payment_status)
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
        "original_delivery_sum": str(delivery_info.get("original_delivery_sum", delivery_info["delivery_sum"])),
        "free_delivery_from": str(delivery_info["free_delivery_from"]) if delivery_info.get("free_delivery_from") else "",
        "free_delivery_applied": bool(delivery_info.get("free_delivery_applied")),
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

    original_delivery_sum = _to_decimal(payload.get("original_delivery_sum")) or delivery_sum
    free_delivery_from = _to_decimal(payload.get("free_delivery_from"))

    return {
        "delivery_type": payload.get("delivery_type") or "cdek_courier",
        "cdek_city_code": payload.get("cdek_city_code") or "",
        "delivery_sum": delivery_sum,
        "original_delivery_sum": original_delivery_sum,
        "free_delivery_from": free_delivery_from,
        "free_delivery_applied": bool(payload.get("free_delivery_applied")),
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
        quote["delivery_sum_label"] = _money_label(quote.get("delivery_sum"))
        quote["original_delivery_sum_label"] = _money_label(quote.get("original_delivery_sum", quote.get("delivery_sum")))
        quote["free_delivery_from_label"] = _money_label(quote.get("free_delivery_from")) if quote.get("free_delivery_from") else ""
        subtotal_after_discount = max(
            context["cart_subtotal"] - context.get("promo_discount", Decimal("0.00")),
            Decimal("0.00"),
        )
        total = subtotal_after_discount + shipping
        context.update({
            "cart_shipping": shipping,
            "cart_shipping_label": _money_label(shipping),
            "cart_subtotal_after_discount": subtotal_after_discount,
            "cart_subtotal_after_discount_label": _money_label(subtotal_after_discount),
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
        release_expired_reservations()
        promo = cart_context.get("promo")
        discount_amount = Decimal("0.00")

        if promo is not None:
            promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
            reason = promo.get_unavailable_reason(cart_context["cart_subtotal"])
            if reason:
                raise ValueError(reason)
            discount_amount = promo.calculate_discount(cart_context["cart_subtotal"])

        order = Order.objects.create(
            customer=request.user,
            delivery_address=_build_delivery_address(checkout_data),
            delivery_type=delivery_type,
            payment_method=payment_method or "yookassa_card",
            payment_status="pending",
            delivery_price=delivery_info["delivery_sum"],
            promo_code=promo,
            discount_amount=discount_amount,
            cdek_city_code=checkout_data.get("cdek_city_code") or None,
            cdek_tariff_code=delivery_info.get("tariff_code"),
            cdek_delivery_period_min=delivery_info.get("period_min"),
            cdek_delivery_period_max=delivery_info.get("period_max"),
        )

        expires_at = get_reservation_expires_at() if _payment_requires_yookassa(payment_method) else None
        create_order_items_and_reservations(
            order,
            cart_context["cart_items"],
            expires_at=expires_at,
        )

        if not _payment_requires_yookassa(payment_method):
            confirm_order_reservations(order)

        if promo is not None and discount_amount > Decimal("0.00"):
            promo.used_count += 1
            promo.save(update_fields=["used_count", "updated_at"])

        order.recalculate_total()

    return order


@customer_required
def checkout(request):
    release_expired_reservations()
    context = _cart_context(request)
    checkout_data = request.session.get(CHECKOUT_SESSION_KEY, {})
    context["checkout_data"] = checkout_data

    if request.method == "POST":
        if not context["cart_items"]:
            messages.error(request, "Нельзя оформить пустую корзину.")
            return redirect("cart")

        if _handle_promo_action(request, context["cart_subtotal"]):
            return redirect("checkout")

        checkout_data = _post_data_to_checkout_session(request.POST)
        if not _checkout_data_is_complete(checkout_data):
            messages.error(request, "Заполните контактные данные и адрес доставки.")
            context["checkout_data"] = checkout_data
            return render(request, "pages/checkout.html", context)

        request.session[CHECKOUT_SESSION_KEY] = checkout_data
        _clear_cdek_quote(request)
        return redirect("checkout_delivery")

    return render(request, "pages/checkout.html", context)


@customer_required
def checkout_delivery(request):
    release_expired_reservations()
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
            delivery_info = _apply_shop_delivery_rules(cart_context, delivery_info)
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
            "original_delivery_sum": delivery_info.get("original_delivery_sum", delivery_info["delivery_sum"]),
            "free_delivery_from": delivery_info.get("free_delivery_from"),
            "free_delivery_applied": delivery_info.get("free_delivery_applied", False),
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

        clear_cart_storage(request)
        request.session.pop(CHECKOUT_SESSION_KEY, None)
        request.session.pop(CDEK_QUOTE_SESSION_KEY, None)
        request.session.pop(PROMO_SESSION_KEY, None)
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

                notify_order_created(order)

                if order.yookassa_confirmation_url:
                    return redirect(order.yookassa_confirmation_url)

                return redirect("checkout_payment", order_number=order.order_number)
            except YooKassaApiError as error:
                order.yookassa_payment_status = "error"
                order.yookassa_error = str(error)
                order.save(update_fields=["yookassa_payment_status", "yookassa_error"])
                notify_order_created(order)
                messages.warning(request, "Заказ создан, но платёж ЮKassa не был сформирован. Проверьте настройки оплаты.")
                return redirect("checkout_payment", order_number=order.order_number)

        notify_order_created(order)
        order_items_total = sum(item.subtotal for item in order.items.all())
        order_items_count = sum(item.quantity for item in order.items.all())
        success_context = _delivery_page_context(request, cart_context, order=order, quote=quote, delivery_input=delivery_input)
        success_context.update({
            "cart_count": order_items_count,
            "cart_subtotal": order_items_total,
            "cart_subtotal_label": _money_label(order_items_total),
            "cart_shipping": order.delivery_price,
            "cart_shipping_label": _money_label(order.delivery_price),
            "promo": order.promo_code,
            "promo_code": order.promo_code.code if order.promo_code else "",
            "promo_discount": order.discount_amount,
            "promo_discount_label": _money_label(order.discount_amount),
            "cart_subtotal_after_discount": max(order_items_total - order.discount_amount, Decimal("0.00")),
            "cart_subtotal_after_discount_label": _money_label(max(order_items_total - order.discount_amount, Decimal("0.00"))),
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
    release_expired_reservations()
    orders = Order.objects.prefetch_related(
        "items__product_variant__product",
        "items__product_variant__color",
        "reservations",
    )

    if not getattr(request.user, "can_manage_shop", False):
        orders = orders.filter(customer=request.user)

    order = get_object_or_404(orders, order_number=order_number)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "demo_success":
            if not settings.YOOKASSA_DEMO_MODE:
                messages.error(request, "Демо-оплата отключена. Проверьте платёж через ЮKassa.")
                return redirect("checkout_payment", order_number=order.order_number)

            if not order.has_active_reservations and order.payment_status != "paid":
                messages.error(request, "Срок резервирования товара истёк. Оформите заказ заново.")
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
        "discount_label": _money_label(order.discount_amount),
        "delivery_price_label": _money_label(order.delivery_price),
        "total_label": _money_label(order.total_amount),
        "yookassa_demo_mode": settings.YOOKASSA_DEMO_MODE,
        "can_demo_pay": settings.YOOKASSA_DEMO_MODE and order.payment_status != "paid" and order.has_active_reservations,
    })


@customer_required
def return_create(request, order_item_id):
    order_items = OrderItem.objects.select_related(
        "order",
        "order__customer",
        "product_variant",
        "product_variant__product",
        "product_variant__color",
    )

    if not getattr(request.user, "can_manage_shop", False):
        order_items = order_items.filter(order__customer=request.user)

    order_item = get_object_or_404(order_items, pk=order_item_id)

    existing_return = getattr(order_item, "return_request", None)
    if existing_return is not None:
        messages.info(request, "Заявка на возврат по этой позиции уже создана.")
        return redirect("return_detail", return_id=existing_return.id)

    if not order_item.can_create_return:
        if order_item.return_period_expired:
            messages.error(
                request,
                f"Срок возврата истёк. По настройкам магазина возврат доступен {order_item.order.return_period_days} дней, до {order_item.order.return_deadline_label}.",
            )
        else:
            messages.error(request, "Возврат доступен только для оплаченных заказов без ранее созданной заявки по выбранному товару.")
        return redirect("users:profile")

    if request.method == "POST":
        form = ReturnRequestForm(request.POST, request.FILES)

        if form.is_valid():
            return_request = form.save(commit=False)
            return_request.order_item = order_item
            return_request.refund_amount = order_item.subtotal
            return_request.save()
            notify_return_request_created(return_request)

            messages.success(request, "Заявка на возврат создана и передана на рассмотрение менеджеру. Подтверждение отправлено на email.")
            return redirect("return_detail", return_id=return_request.id)
    else:
        form = ReturnRequestForm()

    return render(request, "pages/return_create.html", {
        "form": form,
        "order_item": order_item,
        "order": order_item.order,
        "refund_amount_label": _money_label(order_item.subtotal),
        "return_period_days": order_item.order.return_period_days,
        "return_deadline_label": order_item.order.return_deadline_label,
    })


@login_required
def return_detail(request, return_id):
    return_requests = ReturnRequest.objects.select_related(
        "order_item",
        "order_item__order",
        "order_item__order__customer",
        "order_item__product_variant",
        "order_item__product_variant__product",
        "order_item__product_variant__color",
    )

    if not getattr(request.user, "can_manage_shop", False):
        return_requests = return_requests.filter(order_item__order__customer=request.user)

    return_request = get_object_or_404(return_requests, pk=return_id)

    return render(request, "pages/return_detail.html", {
        "return_request": return_request,
        "order_item": return_request.order_item,
        "order": return_request.order_item.order,
        "refund_amount_label": _money_label(return_request.refund_amount or return_request.order_item.subtotal),
        "return_period_days": return_request.order_item.order.return_period_days,
        "return_deadline_label": return_request.order_item.order.return_deadline_label,
    })
