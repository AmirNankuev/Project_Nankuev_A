from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode

from catalog.models import Product, ProductImage, ProductVariant
from main.email_notifications import (
    notify_email_confirmation,
    notify_order_status_changed,
    notify_password_changed,
    notify_return_status_changed,
)
from main.models import CustomerProfile, Order, OrderItem, ReturnRequest

from .decorators import manager_required
from .forms import LoginForm, ProfileForm, RegisterForm
from .models import CustomUser


def _sync_customer_profile(user):
    if not getattr(user, "is_customer_role", False):
        return None

    profile, created = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={
            "phone": user.phone,
            "account_status": "active",
        },
    )

    if not created and profile.phone != user.phone:
        profile.phone = user.phone
        profile.save(update_fields=["phone"])

    return profile


def _choice_values(choices):
    return {value for value, _label in choices}


def _safe_next_or_default(request, default_url):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default_url


class EmailPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("users:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        notify_password_changed(self.request.user)
        messages.success(self.request, "Пароль успешно изменён. Уведомление отправлено на вашу почту.")
        return response


class EmailPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("users:password_reset_done")


class EmailPasswordResetDoneView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class EmailPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("users:password_reset_complete")

    def form_valid(self, form):
        user = self.user
        response = super().form_valid(form)
        if user is not None:
            notify_password_changed(user)
        return response


class EmailPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


def _order_base_queryset():
    order_items_queryset = (
        OrderItem.objects
        .select_related("product_variant", "product_variant__product", "product_variant__color", "return_request")
        .prefetch_related(
            Prefetch(
                "product_variant__product__images",
                queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
                to_attr="staff_main_images",
            )
        )
    )

    return (
        Order.objects
        .select_related("customer", "promo_code")
        .prefetch_related(Prefetch("items", queryset=order_items_queryset))
    )


def _return_base_queryset():
    return (
        ReturnRequest.objects
        .select_related(
            "order_item",
            "order_item__order",
            "order_item__order__customer",
            "order_item__product_variant",
            "order_item__product_variant__product",
            "order_item__product_variant__color",
        )
        .prefetch_related(
            Prefetch(
                "order_item__product_variant__product__images",
                queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
                to_attr="staff_return_images",
            )
        )
    )


def _build_order_status_tabs(active_status):
    tabs = [{
        "value": "",
        "label": "Все",
        "count": Order.objects.count(),
        "active": not active_status,
    }]

    for value, label in Order.STATUS_CHOICES:
        tabs.append({
            "value": value,
            "label": label,
            "count": Order.objects.filter(status=value).count(),
            "active": active_status == value,
        })

    return tabs


def _build_return_status_tabs(active_status):
    tabs = [{
        "value": "",
        "label": "Все",
        "count": ReturnRequest.objects.count(),
        "active": not active_status,
    }]

    for value, label in ReturnRequest.STATUS_CHOICES:
        tabs.append({
            "value": value,
            "label": label,
            "count": ReturnRequest.objects.filter(status=value).count(),
            "active": active_status == value,
        })

    return tabs


def _parse_refund_amount(raw_value, fallback):
    if raw_value in (None, ""):
        return fallback

    try:
        value = Decimal(str(raw_value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("Сумма возврата должна быть числом.")

    if value < Decimal("0.00"):
        raise ValueError("Сумма возврата не может быть отрицательной.")

    return value


def _complete_return_request(return_request, refund_amount):
    if return_request.status in {"completed", "rejected"}:
        return False

    order_item = return_request.order_item
    order = order_item.order
    variant = order_item.product_variant

    with transaction.atomic():
        locked_return = (
            ReturnRequest.objects
            .select_for_update()
            .select_related("order_item", "order_item__order", "order_item__product_variant")
            .get(pk=return_request.pk)
        )

        if locked_return.status in {"completed", "rejected"}:
            return False

        locked_return.status = "completed"
        locked_return.refund_amount = refund_amount
        locked_return.resolved_at = timezone.now()
        locked_return.save(update_fields=["status", "refund_amount", "resolved_at"])

        # Если товар в нормальном состоянии, менеджер возвращает его на склад.
        if locked_return.condition == "new":
            locked_variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
            locked_variant.quantity += order_item.quantity
            locked_variant.save(update_fields=["quantity"])

        order_items_count = order.items.count()
        completed_returns_count = ReturnRequest.objects.filter(
            order_item__order=order,
            status="completed",
        ).count()

        if order_items_count and completed_returns_count == order_items_count:
            order.status = "returned"
            order.payment_status = "refunded"
            order.save(update_fields=["status", "payment_status"])

    return True


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = False
                user.email_confirmed = False
                user.save()
                form.save_m2m()
                CustomerProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "phone": user.phone,
                        "account_status": "active",
                    },
                )

            if notify_email_confirmation(user):
                messages.success(request, "Аккаунт создан. На вашу почту отправлена ссылка для подтверждения.")
            else:
                messages.warning(
                    request,
                    "Аккаунт создан, но письмо подтверждения не удалось отправить. Проверьте SMTP-настройки.",
                )
            return redirect("users:email_confirmation_sent")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {
        "form": form
    })


def email_confirmation_sent_view(request):
    if request.user.is_authenticated:
        return redirect("users:profile")

    return render(request, "registration/email_confirmation_sent.html")


def email_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        with transaction.atomic():
            user.is_active = True
            user.email_confirmed = True
            user.save(update_fields=["is_active", "email_confirmed"])
            CustomerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "phone": user.phone,
                    "account_status": "active",
                },
            )

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Email подтверждён. Аккаунт активирован.")
        return redirect("users:profile")

    return render(request, "registration/email_confirm_invalid.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if getattr(user, "can_manage_shop", False):
                return redirect("users:staff_dashboard")
            return redirect("home")
    else:
        form = LoginForm()

    return render(request, "registration/login.html", {
        "form": form
    })


@login_required
def profile_view(request):
    if getattr(request.user, "can_manage_shop", False):
        return redirect("users:staff_dashboard")

    profile = _sync_customer_profile(request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                profile.phone = user.phone
                profile.save(update_fields=["phone"])
            messages.success(request, "Данные личного кабинета обновлены.")
            return redirect("users:profile")
    else:
        form = ProfileForm(instance=request.user)

    order_items_queryset = (
        OrderItem.objects
        .select_related("product_variant", "product_variant__product", "product_variant__color", "return_request")
        .prefetch_related(
            Prefetch(
                "product_variant__product__images",
                queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
                to_attr="profile_main_images",
            )
        )
    )

    orders = (
        Order.objects
        .filter(customer=request.user)
        .select_related("promo_code")
        .prefetch_related(Prefetch("items", queryset=order_items_queryset))
        .order_by("-created_at")
    )

    return render(request, "registration/profile.html", {
        "form": form,
        "profile": profile,
        "orders": orders,
    })


@manager_required
def staff_dashboard(request):
    recent_orders = (
        Order.objects
        .select_related("customer", "promo_code")
        .order_by("-created_at")[:8]
    )
    recent_returns = (
        ReturnRequest.objects
        .select_related(
            "order_item",
            "order_item__order",
            "order_item__order__customer",
            "order_item__product_variant",
            "order_item__product_variant__product",
        )
        .order_by("-created_at")[:8]
    )
    low_stock_variants = (
        ProductVariant.objects
        .select_related("product", "color")
        .filter(quantity__lte=3)
        .order_by("quantity", "product__name")[:10]
    )

    context = {
        "orders_total": Order.objects.count(),
        "orders_paid": Order.objects.filter(status="paid").count(),
        "orders_processing": Order.objects.filter(status__in=["paid", "processing", "assembled"]).count(),
        "orders_ready_to_ship": Order.objects.filter(status="assembled").count(),
        "orders_shipped": Order.objects.filter(status="shipped").count(),
        "returns_requested": ReturnRequest.objects.filter(status="requested").count(),
        "returns_approved": ReturnRequest.objects.filter(status="approved").count(),
        "products_total": Product.objects.count(),
        "low_stock_count": ProductVariant.objects.filter(quantity__lte=3).count(),
        "recent_orders": recent_orders,
        "recent_returns": recent_returns,
        "low_stock_variants": low_stock_variants,
    }

    return render(request, "registration/staff_dashboard.html", context)


@manager_required
def staff_orders(request):
    valid_statuses = _choice_values(Order.STATUS_CHOICES)
    valid_payment_statuses = _choice_values(Order.PAYMENT_STATUS_CHOICES)

    if request.method == "POST":
        order = get_object_or_404(Order, pk=request.POST.get("order_id"))
        new_status = request.POST.get("status")
        new_payment_status = request.POST.get("payment_status")
        tracking_number = request.POST.get("tracking_number", "").strip()

        if new_status not in valid_statuses:
            messages.error(request, "Выбран некорректный статус заказа.")
        elif new_payment_status not in valid_payment_statuses:
            messages.error(request, "Выбран некорректный статус оплаты.")
        else:
            old_status = order.status
            old_payment_status = order.payment_status
            old_tracking_number = order.tracking_number

            order.status = new_status
            order.payment_status = new_payment_status
            order.tracking_number = tracking_number or None
            order.save(update_fields=["status", "payment_status", "tracking_number", "updated_at"])
            notify_order_status_changed(
                order,
                old_status=old_status,
                old_payment_status=old_payment_status,
                old_tracking_number=old_tracking_number,
            )
            messages.success(request, f"Заказ {order.order_number} обновлён. Если данные изменились, покупателю отправлено письмо.")

        return redirect(_safe_next_or_default(request, reverse("users:staff_orders")))

    active_status = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()

    orders = _order_base_queryset().order_by("-created_at")

    if active_status in valid_statuses:
        orders = orders.filter(status=active_status)
    else:
        active_status = ""

    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query)
            | Q(customer__username__icontains=search_query)
            | Q(customer__email__icontains=search_query)
            | Q(customer__full_name__icontains=search_query)
            | Q(delivery_address__icontains=search_query)
            | Q(tracking_number__icontains=search_query)
        )

    paginator = Paginator(orders, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "orders": page_obj.object_list,
        "active_status": active_status,
        "search_query": search_query,
        "status_tabs": _build_order_status_tabs(active_status),
        "order_status_choices": Order.STATUS_CHOICES,
        "payment_status_choices": Order.PAYMENT_STATUS_CHOICES,
    }
    return render(request, "registration/staff_orders.html", context)


@manager_required
def staff_order_detail(request, order_id):
    order = get_object_or_404(_order_base_queryset(), pk=order_id)
    valid_statuses = _choice_values(Order.STATUS_CHOICES)
    valid_payment_statuses = _choice_values(Order.PAYMENT_STATUS_CHOICES)

    if request.method == "POST":
        new_status = request.POST.get("status")
        new_payment_status = request.POST.get("payment_status")
        tracking_number = request.POST.get("tracking_number", "").strip()

        if new_status not in valid_statuses:
            messages.error(request, "Выбран некорректный статус заказа.")
        elif new_payment_status not in valid_payment_statuses:
            messages.error(request, "Выбран некорректный статус оплаты.")
        else:
            old_status = order.status
            old_payment_status = order.payment_status
            old_tracking_number = order.tracking_number

            order.status = new_status
            order.payment_status = new_payment_status
            order.tracking_number = tracking_number or None
            order.save(update_fields=["status", "payment_status", "tracking_number", "updated_at"])
            notify_order_status_changed(
                order,
                old_status=old_status,
                old_payment_status=old_payment_status,
                old_tracking_number=old_tracking_number,
            )
            messages.success(request, f"Заказ {order.order_number} обновлён. Если данные изменились, покупателю отправлено письмо.")
            return redirect("users:staff_order_detail", order_id=order.id)

    items_total = sum(item.subtotal for item in order.items.all())
    context = {
        "order": order,
        "order_items": order.items.all(),
        "items_total": items_total,
        "order_status_choices": Order.STATUS_CHOICES,
        "payment_status_choices": Order.PAYMENT_STATUS_CHOICES,
    }
    return render(request, "registration/staff_order_detail.html", context)


@manager_required
def staff_returns(request):
    valid_statuses = _choice_values(ReturnRequest.STATUS_CHOICES)

    if request.method == "POST":
        return_request = get_object_or_404(_return_base_queryset(), pk=request.POST.get("return_id"))
        action = request.POST.get("action")

        try:
            refund_amount = _parse_refund_amount(
                request.POST.get("refund_amount"),
                return_request.refund_amount or return_request.order_item.subtotal,
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect(_safe_next_or_default(request, reverse("users:staff_returns")))

        if action == "approve":
            if return_request.status in {"completed", "rejected"}:
                messages.error(request, "Завершённый или отклонённый возврат нельзя одобрить повторно.")
            else:
                old_status = return_request.status
                return_request.status = "approved"
                return_request.refund_amount = refund_amount
                return_request.resolved_at = None
                return_request.save(update_fields=["status", "refund_amount", "resolved_at"])
                notify_return_status_changed(return_request, old_status=old_status)
                messages.success(request, "Возврат одобрен. Покупателю отправлено уведомление.")
        elif action == "reject":
            if return_request.status == "completed":
                messages.error(request, "Завершённый возврат нельзя отклонить.")
            else:
                old_status = return_request.status
                return_request.status = "rejected"
                return_request.refund_amount = refund_amount
                return_request.resolved_at = timezone.now()
                return_request.save(update_fields=["status", "refund_amount", "resolved_at"])
                notify_return_status_changed(return_request, old_status=old_status)
                messages.warning(request, "Возврат отклонён. Покупателю отправлено уведомление.")
        elif action == "complete":
            old_status = return_request.status
            completed = _complete_return_request(return_request, refund_amount)
            if completed:
                return_request.refresh_from_db()
                notify_return_status_changed(return_request, old_status=old_status)
                messages.success(request, "Возврат завершён. Если товар новый, остаток на складе увеличен. Покупателю отправлено уведомление.")
            else:
                messages.info(request, "Возврат уже был завершён или отклонён.")
        else:
            messages.error(request, "Неизвестное действие с возвратом.")

        return redirect(_safe_next_or_default(request, reverse("users:staff_returns")))

    active_status = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()

    returns = _return_base_queryset().order_by("-created_at")

    if active_status in valid_statuses:
        returns = returns.filter(status=active_status)
    else:
        active_status = ""

    if search_query:
        returns = returns.filter(
            Q(reason__icontains=search_query)
            | Q(order_item__order__order_number__icontains=search_query)
            | Q(order_item__order__customer__username__icontains=search_query)
            | Q(order_item__order__customer__email__icontains=search_query)
            | Q(order_item__order__customer__full_name__icontains=search_query)
            | Q(order_item__product_variant__product__name__icontains=search_query)
        )

    paginator = Paginator(returns, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "returns": page_obj.object_list,
        "active_status": active_status,
        "search_query": search_query,
        "status_tabs": _build_return_status_tabs(active_status),
    }
    return render(request, "registration/staff_returns.html", context)


@manager_required
def staff_return_detail(request, return_id):
    return_request = get_object_or_404(_return_base_queryset(), pk=return_id)

    if request.method == "POST":
        try:
            refund_amount = _parse_refund_amount(
                request.POST.get("refund_amount"),
                return_request.refund_amount or return_request.order_item.subtotal,
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("users:staff_return_detail", return_id=return_request.id)

        action = request.POST.get("action")
        if action == "approve":
            if return_request.status in {"completed", "rejected"}:
                messages.error(request, "Завершённый или отклонённый возврат нельзя одобрить повторно.")
            else:
                old_status = return_request.status
                return_request.status = "approved"
                return_request.refund_amount = refund_amount
                return_request.resolved_at = None
                return_request.save(update_fields=["status", "refund_amount", "resolved_at"])
                notify_return_status_changed(return_request, old_status=old_status)
                messages.success(request, "Возврат одобрен. Покупателю отправлено уведомление.")
        elif action == "reject":
            if return_request.status == "completed":
                messages.error(request, "Завершённый возврат нельзя отклонить.")
            else:
                old_status = return_request.status
                return_request.status = "rejected"
                return_request.refund_amount = refund_amount
                return_request.resolved_at = timezone.now()
                return_request.save(update_fields=["status", "refund_amount", "resolved_at"])
                notify_return_status_changed(return_request, old_status=old_status)
                messages.warning(request, "Возврат отклонён. Покупателю отправлено уведомление.")
        elif action == "complete":
            old_status = return_request.status
            completed = _complete_return_request(return_request, refund_amount)
            if completed:
                return_request.refresh_from_db()
                notify_return_status_changed(return_request, old_status=old_status)
                messages.success(request, "Возврат завершён. Если товар новый, остаток на складе увеличен. Покупателю отправлено уведомление.")
            else:
                messages.info(request, "Возврат уже был завершён или отклонён.")
        else:
            messages.error(request, "Неизвестное действие с возвратом.")

        return redirect("users:staff_return_detail", return_id=return_request.id)

    context = {
        "return_request": return_request,
        "order_item": return_request.order_item,
        "order": return_request.order_item.order,
        "refund_amount": return_request.refund_amount or return_request.order_item.subtotal,
    }
    return render(request, "registration/staff_return_detail.html", context)
