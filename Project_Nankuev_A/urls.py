"""
URL configuration for Project_Nankuev_A project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from main.views import home
from catalog import views as catalog_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("catalog/", include("catalog.urls")),
    path("cart/", catalog_views.cart_detail, name="cart"),
    path("cart/add/<int:variant_id>/", catalog_views.cart_add, name="cart_add"),
    path("cart/add-product/<int:product_id>/", catalog_views.cart_add_product, name="cart_add_product"),
    path("cart/update/<int:variant_id>/", catalog_views.cart_update, name="cart_update"),
    path("cart/remove/<int:variant_id>/", catalog_views.cart_remove, name="cart_remove"),
    path("checkout/", catalog_views.checkout, name="checkout"),
    path("checkout/delivery/", catalog_views.checkout_delivery, name="checkout_delivery"),
    path("checkout/payment/<str:order_number>/", catalog_views.checkout_payment, name="checkout_payment"),
    path("users/", include("users.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
