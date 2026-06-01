from django.db.models import Prefetch, Q
from django.shortcuts import render

from catalog.models import Product, ProductImage, ProductVariant


def _fill_products(products, count, start=0):
    if not products:
        return []

    selected = list(products[start:start + count])
    index = 0

    while len(selected) < count:
        selected.append(products[index % len(products)])
        index += 1

    return selected


def home(request):
    search_query = request.GET.get("search", "").strip()

    products_queryset = Product.objects.filter(
        is_active=True,
    ).select_related(
        "brand",
        "category",
    ).prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
            to_attr="main_images",
        ),
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("color").order_by("color__name", "size"),
            to_attr="prepared_variants",
        )
    ).order_by("-created_at")

    if search_query:
        products_queryset = products_queryset.filter(
            Q(name__icontains=search_query)
            | Q(article__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(brand__name__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    products_count = products_queryset.count()
    products = list(products_queryset[:20])

    context = {
        "search_query": search_query,
        "hero_products": _fill_products(products, 2, 0),
        "new_products": _fill_products(products, 4, 0),
        "collection_products": _fill_products(products, 3, 4),
        "gallery_products": _fill_products(products, 4, 7),
        "products_count": products_count,
    }

    return render(request, "pages/home.html", context)
