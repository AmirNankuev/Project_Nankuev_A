from django.contrib import admin

from .models import CustomerProfile, Order, OrderItem, ReturnRequest, CartItem


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "phone", "account_status", "registration_date")
    search_fields = ("user__username", "user__email", "phone")
    list_filter = ("account_status",)
    ordering = ("-registration_date",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_variant", "quantity", "unit_price", "subtotal")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_number",
        "customer",
        "status",
        "payment_status",
        "total_amount",
        "created_at",
    )
    list_display_links = ("id", "order_number")
    search_fields = (
        "order_number",
        "customer__username",
        "customer__email",
        "delivery_address",
    )
    list_filter = ("status", "payment_status", "delivery_type", "payment_method", "created_at")
    readonly_fields = ("order_number", "customer", "total_amount", "created_at", "updated_at")
    inlines = (OrderItemInline,)
    ordering = ("-created_at",)
    fieldsets = (
        ("Основное", {
            "fields": ("order_number", "customer", "status", "total_amount"),
        }),
        ("Доставка и оплата", {
            "fields": ("delivery_address", "delivery_type", "payment_method", "payment_status", "tracking_number"),
        }),
        ("Служебные данные", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product_variant", "quantity", "unit_price", "subtotal")
    search_fields = ("order__order_number", "product_variant__product__name")
    ordering = ("order",)


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "order_item", "condition", "status", "refund_amount", "created_at")
    search_fields = ("reason", "order_item__order__order_number")
    list_filter = ("condition", "status")
    ordering = ("-created_at",)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "product_variant", "quantity", "added_at")
    search_fields = ("customer__username", "product_variant__product__name")
    ordering = ("-added_at",)
