from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from image_uploader_widget.admin import ImageUploaderInline
from image_uploader_widget.widgets import ImageUploaderWidget

from .forms import ProductImageInlineForm, ProductImageInlineFormSet
from .models import Brand, Category, Collection, Color, Product, ProductImage, ProductReview, ProductVariant


def normalize_product_images(product):
    if not product or not product.pk:
        return

    images = list(product.images.order_by("sort_order", "id"))
    if not images:
        return

    main_image = images[0]
    ProductImage.objects.filter(product=product).exclude(pk=main_image.pk).update(is_main=False)
    if not main_image.is_main:
        ProductImage.objects.filter(pk=main_image.pk).update(is_main=True)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = (
        "color",
        "size",
        "quantity",
        "pricing_type",
        "markup_percent",
        "site_price",
        "final_price_display",
    )
    readonly_fields = ("final_price_display",)

    @admin.display(description="Итоговая цена на сайте")
    def final_price_display(self, obj):
        if not obj or not obj.pk:
            return "Появится после сохранения"

        return obj.public_price_label


class ProductImageInline(ImageUploaderInline):
    model = ProductImage
    form = ProductImageInlineForm
    formset = ProductImageInlineFormSet
    extra = 1
    fields = ("drag_handle", "image", "preview", "main_badge", "sort_order")
    readonly_fields = ("drag_handle", "preview", "main_badge")

    class Media:
        js = ("catalog/admin_product_images.js",)
        css = {"all": ("catalog/admin_product_images.css",)}

    @admin.display(description=" ")
    def drag_handle(self, obj):
        return format_html(
            '<span class="product-image-drag-handle" title="Перетащите фото выше или ниже">↕</span>'
        )

    @admin.display(description="Превью")
    def preview(self, obj):
        if not obj or not obj.image:
            return "—"
        return format_html(
            '<img src="{}" class="product-image-admin-preview" alt="Превью" />',
            obj.image.url,
        )

    @admin.display(description="Статус")
    def main_badge(self, obj):
        label = "Главная" if obj and obj.is_main else "Доп."
        return format_html('<span class="product-image-main-badge">{}</span>', label)


class ProductReviewInline(admin.TabularInline):
    model = ProductReview
    extra = 0
    fields = ("customer", "rating", "status", "text", "created_at")
    readonly_fields = ("customer", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    fields = ("name", "gender", "parent", "slug")
    list_display = ("id", "name", "gender", "slug", "parent")
    readonly_fields = ("slug",)
    search_fields = ("name", "slug")
    list_filter = ("gender", "parent")
    ordering = ("gender", "parent__name", "name")


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "season",
        "year",
        "is_active",
        "sort_order",
        "products_count",
    )
    fields = (
        "name",
        "slug",
        "season",
        "year",
        "description",
        "is_active",
        "sort_order",
    )
    readonly_fields = ("slug",)
    search_fields = ("name", "slug", "season", "description")
    list_filter = ("is_active", "season", "year")
    ordering = ("sort_order", "-year", "name")

    @admin.display(description="Товаров")
    def products_count(self, obj):
        return obj.products.count()


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "hex_code")
    search_fields = ("name", "hex_code")
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "article",
        "name",
        "slug",
        "brand",
        "category",
        "collection_names",
        "price_from_display",
        "rating_display",
        "reviews_count_display",
        "is_active",
        "created_at",
    )
    readonly_fields = ("slug", "price_from_display")
    search_fields = ("article", "name", "slug", "description")
    list_filter = ("brand", "category", "collections", "is_active")
    ordering = ("-created_at",)
    filter_horizontal = ("collections",)
    inlines = [ProductVariantInline, ProductImageInline, ProductReviewInline]
    fieldsets = (
        ("Основная информация", {
            "fields": (
                "article",
                "name",
                "slug",
                "description",
                "brand",
                "category",
                "collections",
                "is_active",
            )
        }),
        ("Закупочная цена", {
            "fields": ("price",),
            "description": (
                "Это внутренняя базовая цена закупки. Покупателям она не показывается. "
                "Цены на сайте задаются в вариантах товара через процентную наценку или готовую цену."
            ),
        }),
        ("Публичное отображение", {
            "fields": ("price_from_display",),
        }),
    )


    @admin.display(description="Коллекции")
    def collection_names(self, obj):
        collections = list(obj.collections.all()[:3])
        if not collections:
            return "—"

        names = ", ".join(collection.name for collection in collections)
        if obj.collections.count() > 3:
            names += " …"
        return names

    @admin.display(description="Цена на сайте")
    def price_from_display(self, obj):
        if not obj or not obj.pk:
            return "Появится после добавления вариантов"

        return obj.price_from_label

    @admin.display(description="Рейтинг")
    def rating_display(self, obj):
        if not obj.reviews_count:
            return "—"
        return obj.average_rating_label

    @admin.display(description="Отзывов")
    def reviews_count_display(self, obj):
        return obj.reviews_count

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        normalize_product_images(form.instance)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "color",
        "size",
        "quantity",
        "pricing_type",
        "markup_percent",
        "site_price",
        "final_price_display",
    )
    fields = (
        "product",
        "color",
        "size",
        "quantity",
        "pricing_type",
        "markup_percent",
        "site_price",
        "final_price_display",
    )
    readonly_fields = ("final_price_display",)
    search_fields = ("product__name", "product__article", "color__name", "size")
    list_filter = ("pricing_type", "color", "size")
    ordering = ("product", "color", "size")

    @admin.display(description="Итоговая цена на сайте")
    def final_price_display(self, obj):
        if not obj or not obj.pk:
            return "Появится после сохранения"

        return obj.public_price_label


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.ImageField: {"widget": ImageUploaderWidget},
    }
    list_display = ("id", "product", "preview", "is_main", "sort_order")
    search_fields = ("product__name", "image")
    list_filter = ("is_main",)
    ordering = ("product", "sort_order", "id")

    @admin.display(description="Превью")
    def preview(self, obj):
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" class="product-image-admin-preview" alt="Превью" />',
            obj.image.url,
        )

    def save_model(self, request, obj, form, change):
        if obj.is_main and obj.product_id:
            ProductImage.objects.filter(product=obj.product).exclude(pk=obj.pk).update(is_main=False)
        super().save_model(request, obj, form, change)
        normalize_product_images(obj.product)

    def delete_model(self, request, obj):
        product = obj.product
        super().delete_model(request, obj)
        normalize_product_images(product)

    def delete_queryset(self, request, queryset):
        products = list({image.product for image in queryset.select_related("product")})
        super().delete_queryset(request, queryset)
        for product in products:
            normalize_product_images(product)

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "customer",
        "rating",
        "status",
        "created_at",
    )
    list_display_links = ("id", "product")
    search_fields = (
        "product__name",
        "product__article",
        "customer__username",
        "customer__email",
        "customer__full_name",
        "text",
    )
    list_filter = ("rating", "status", "created_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    actions = ("publish_reviews", "reject_reviews")

    @admin.action(description="Опубликовать выбранные отзывы")
    def publish_reviews(self, request, queryset):
        updated = queryset.update(status=ProductReview.Status.PUBLISHED)
        self.message_user(request, f"Опубликовано отзывов: {updated}")

    @admin.action(description="Отклонить выбранные отзывы")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(status=ProductReview.Status.REJECTED)
        self.message_user(request, f"Отклонено отзывов: {updated}")

