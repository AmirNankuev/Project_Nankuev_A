from django.contrib import admin, messages
from django.utils import timezone

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
        "yookassa_payment_status",
        "total_amount",
        "delivery_price",
        "cdek_status",
        "created_at",
    )
    list_display_links = ("id", "order_number")
    search_fields = (
        "order_number",
        "customer__username",
        "customer__email",
        "delivery_address",
        "tracking_number",
        "cdek_uuid",
        "yookassa_payment_id",
    )
    list_filter = ("status", "payment_status", "yookassa_payment_status", "delivery_type", "payment_method", "cdek_status", "created_at")
    readonly_fields = ("order_number", "customer", "total_amount", "cdek_response", "cdek_error", "yookassa_response", "yookassa_error", "created_at", "updated_at")
    inlines = (OrderItemInline,)
    ordering = ("-created_at",)
    fieldsets = (
        ("Основное", {
            "fields": ("order_number", "customer", "status", "total_amount"),
        }),
        ("Доставка и оплата", {
            "fields": ("delivery_address", "delivery_type", "delivery_price", "payment_method", "payment_status", "tracking_number"),
        }),
        ("ЮKassa", {
            "fields": (
                "yookassa_payment_id",
                "yookassa_payment_status",
                "yookassa_confirmation_url",
                "yookassa_error",
                "yookassa_response",
            ),
        }),
        ("СДЭК", {
            "fields": (
                "cdek_city_code",
                "cdek_tariff_code",
                "cdek_delivery_period_min",
                "cdek_delivery_period_max",
                "cdek_uuid",
                "cdek_status",
                "cdek_error",
                "cdek_response",
            ),
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
    list_display = (
        "id",
        "order_number",
        "customer",
        "product_name",
        "condition",
        "status",
        "refund_amount",
        "created_at",
        "resolved_at",
    )
    search_fields = (
        "reason",
        "order_item__order__order_number",
        "order_item__order__customer__username",
        "order_item__order__customer__email",
        "order_item__product_variant__product__name",
    )
    list_filter = ("condition", "status", "created_at")
    readonly_fields = ("created_at", "resolved_at")
    ordering = ("-created_at",)
    actions = ("approve_returns", "reject_returns", "complete_returns")

    @admin.display(description="Заказ")
    def order_number(self, obj):
        return obj.order_item.order.order_number

    @admin.display(description="Покупатель")
    def customer(self, obj):
        return obj.order_item.order.customer

    @admin.display(description="Товар")
    def product_name(self, obj):
        return obj.order_item.product_variant.product.name

    @admin.action(description="Одобрить выбранные возвраты")
    def approve_returns(self, request, queryset):
        updated = queryset.exclude(status__in=("completed", "rejected")).update(status="approved")
        self.message_user(request, f"Одобрено возвратов: {updated}.", messages.SUCCESS)

    @admin.action(description="Отклонить выбранные возвраты")
    def reject_returns(self, request, queryset):
        updated = queryset.exclude(status="completed").update(status="rejected", resolved_at=timezone.now())
        self.message_user(request, f"Отклонено возвратов: {updated}.", messages.WARNING)

    @admin.action(description="Завершить выбранные возвраты")
    def complete_returns(self, request, queryset):
        completed = 0

        for return_request in queryset.select_related(
            "order_item",
            "order_item__order",
            "order_item__product_variant",
        ):
            if return_request.status in ("completed", "rejected"):
                continue

            if return_request.refund_amount is None:
                return_request.refund_amount = return_request.order_item.subtotal

            return_request.status = "completed"
            return_request.resolved_at = timezone.now()
            return_request.save(update_fields=["status", "refund_amount", "resolved_at"])

            if return_request.condition == "new":
                variant = return_request.order_item.product_variant
                variant.quantity += return_request.order_item.quantity
                variant.save(update_fields=["quantity"])

            completed += 1

        self.message_user(request, f"Завершено возвратов: {completed}.", messages.SUCCESS)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "product_variant", "quantity", "added_at")
    search_fields = ("customer__username", "product_variant__product__name")
    ordering = ("-added_at",)
