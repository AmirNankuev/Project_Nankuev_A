from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.shortcuts import render, get_object_or_404

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

    if category_id:
        products_queryset = products_queryset.filter(category_id=category_id)

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

    all_categories = list(Category.objects.select_related("parent").order_by("name"))
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
        "selected_category": category_id,
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

    variant_options = []
    for variant in variants:
        variant_options.append({
            "size": variant.size,
            "color_name": variant.color.name,
            "color_hex": variant.color.hex_code,
            "price_label": variant.public_price_label,
            "quantity": variant.quantity,
        })

    selected_variant = next((variant for variant in variants if variant.quantity > 0), variants[0] if variants else None)
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
        "similar_products": similar_products,
    }


def product_detail(request, slug):
    product = get_object_or_404(_product_queryset(), slug=slug)
    return render(request, "pages/product_detail.html", _product_detail_context(product))


def product_detail_by_pk(request, pk):
    product = get_object_or_404(_product_queryset(), pk=pk)
    return render(request, "pages/product_detail.html", _product_detail_context(product))
