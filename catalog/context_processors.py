from django.urls import reverse

from .models import Category


def header_navigation(request):
    root_categories = (
        Category.objects
        .filter(parent__isnull=True)
        .prefetch_related("children")
        .order_by("name")
    )

    return {
        "header_root_categories": root_categories,
        "catalog_url": reverse("catalog:product_list"),
    }



def cart_counter(request):
    cart = request.session.get("cart", {}) if hasattr(request, "session") else {}
    count = 0

    if isinstance(cart, dict):
        for item in cart.values():
            try:
                count += int(item.get("quantity", 0))
            except (AttributeError, TypeError, ValueError):
                continue

    return {"header_cart_count": count}
