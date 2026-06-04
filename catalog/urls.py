from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("products/<slug:slug>/review/", views.add_product_review, name="add_product_review"),
    path("products/id/<int:pk>/", views.product_detail_by_pk, name="product_detail_by_pk"),
]
