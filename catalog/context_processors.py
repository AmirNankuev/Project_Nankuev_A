from django.urls import reverse

from .cart_services import get_cart_count
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
    return {"header_cart_count": get_cart_count(request)}
