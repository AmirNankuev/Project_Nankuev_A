import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

logger = logging.getLogger(__name__)


def _money(value):
    if value is None:
        value = 0
    return f"{value} ₽"


def _site_url(path=""):
    base_url = getattr(settings, "SITE_URL", "").rstrip("/")
    if not base_url:
        return path
    if not path:
        return base_url
    return f"{base_url}{path}"


def _recipient(user):
    email = (getattr(user, "email", "") or "").strip()
    return [email] if email else []


def _send_user_email(user, subject, message):
    if not getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True):
        return False

    recipients = _recipient(user)
    if not recipients:
        logger.info("Email notification skipped: user %s has no email", getattr(user, "pk", None))
        return False

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Email notification failed for user %s", getattr(user, "pk", None))
        return False

    return True


def notify_email_confirmation(user):
    """Send email confirmation link after registration."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    try:
        confirm_path = reverse("users:email_confirm", kwargs={"uidb64": uid, "token": token})
        confirm_url = _site_url(confirm_path)
    except Exception:
        confirm_url = ""

    message = (
        f"Здравствуйте, {getattr(user, 'full_name', '') or getattr(user, 'username', '')}!\n\n"
        f"Вы зарегистрировались в интернет-магазине одежды.\n"
        f"Чтобы активировать аккаунт, подтвердите адрес электронной почты по ссылке ниже:\n\n"
        f"{confirm_url}\n\n"
        f"Если вы не регистрировались в магазине, просто проигнорируйте это письмо."
    )

    return _send_user_email(user, "Подтверждение электронной почты", message)


def notify_order_created(order):
    """Send a confirmation email after the order is created."""
    payment_url = ""
    if getattr(order, "yookassa_confirmation_url", ""):
        payment_url = order.yookassa_confirmation_url
    else:
        try:
            payment_url = _site_url(reverse("checkout_payment", kwargs={"order_number": order.order_number}))
        except Exception:
            payment_url = ""

    items = list(order.items.select_related("product_variant__product", "product_variant__color"))
    item_lines = []
    for item in items:
        product = item.product_variant.product
        color = getattr(item.product_variant.color, "name", "")
        variant_info = " / ".join(part for part in [color, item.product_variant.size] if part)
        item_lines.append(
            f"- {product.name} ({variant_info}) — {item.quantity} × {_money(item.unit_price)} = {_money(item.subtotal)}"
        )

    promo_line = ""
    if order.promo_code and order.discount_amount:
        promo_line = f"\nПромокод: {order.promo_code.code}\nСкидка: {_money(order.discount_amount)}"

    payment_line = f"\nСсылка на оплату/страницу заказа: {payment_url}" if payment_url else ""

    message = (
        f"Здравствуйте!\n\n"
        f"Ваш заказ {order.order_number} успешно оформлен.\n\n"
        f"Состав заказа:\n" + "\n".join(item_lines) + "\n\n"
        f"Доставка: {_money(order.delivery_price)}"
        f"{promo_line}\n"
        f"Итого: {_money(order.total_amount)}\n"
        f"Статус заказа: {order.get_status_display()}\n"
        f"Статус оплаты: {order.get_payment_status_display()}"
        f"{payment_line}\n\n"
        f"Спасибо за покупку!"
    )

    return _send_user_email(order.customer, f"Заказ {order.order_number} оформлен", message)


def notify_order_status_changed(order, old_status=None, old_payment_status=None, old_tracking_number=None):
    """Notify customer when order status, payment status or tracking number changed."""
    status_changed = old_status is not None and old_status != order.status
    payment_changed = old_payment_status is not None and old_payment_status != order.payment_status
    tracking_changed = old_tracking_number is not None and old_tracking_number != order.tracking_number

    if not (status_changed or payment_changed or tracking_changed):
        return False

    lines = [
        f"Здравствуйте!",
        "",
        f"По заказу {order.order_number} обновлена информация.",
        "",
    ]

    if status_changed:
        lines.append(f"Новый статус заказа: {order.get_status_display()}")
    if payment_changed:
        lines.append(f"Новый статус оплаты: {order.get_payment_status_display()}")
    if tracking_changed and order.tracking_number:
        lines.append(f"Трек-номер доставки: {order.tracking_number}")

    lines.extend([
        "",
        f"Сумма заказа: {_money(order.total_amount)}",
        "",
        "Спасибо, что пользуетесь нашим магазином!",
    ])

    return _send_user_email(order.customer, f"Обновление заказа {order.order_number}", "\n".join(lines))


def notify_return_request_created(return_request):
    order_item = return_request.order_item
    order = order_item.order
    product = order_item.product_variant.product

    message = (
        f"Здравствуйте!\n\n"
        f"Ваша заявка на возврат по заказу {order.order_number} создана и передана менеджеру.\n\n"
        f"Товар: {product.name}\n"
        f"Количество: {order_item.quantity}\n"
        f"Причина: {return_request.reason}\n"
        f"Состояние товара: {return_request.get_condition_display()}\n"
        f"Сумма к возврату: {_money(return_request.refund_amount or order_item.subtotal)}\n"
        f"Текущий статус: {return_request.get_status_display()}\n\n"
        f"Мы уведомим вас после обработки заявки."
    )

    return _send_user_email(order.customer, f"Заявка на возврат по заказу {order.order_number}", message)


def notify_return_status_changed(return_request, old_status=None):
    if old_status is not None and old_status == return_request.status:
        return False

    order_item = return_request.order_item
    order = order_item.order
    product = order_item.product_variant.product

    resolved_line = ""
    if return_request.resolved_at:
        resolved_at = timezone.localtime(return_request.resolved_at).strftime("%d.%m.%Y %H:%M")
        resolved_line = f"\nДата обработки: {resolved_at}"

    message = (
        f"Здравствуйте!\n\n"
        f"Статус вашей заявки на возврат по заказу {order.order_number} изменён.\n\n"
        f"Товар: {product.name}\n"
        f"Новый статус: {return_request.get_status_display()}\n"
        f"Сумма возврата: {_money(return_request.refund_amount or order_item.subtotal)}"
        f"{resolved_line}\n\n"
        f"Спасибо за обращение."
    )

    return _send_user_email(order.customer, f"Обновление возврата по заказу {order.order_number}", message)


def notify_password_changed(user):
    changed_at = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")
    message = (
        f"Здравствуйте!\n\n"
        f"Пароль от вашего аккаунта в интернет-магазине был успешно изменён.\n"
        f"Дата и время изменения: {changed_at}.\n\n"
        f"Если это были не вы, срочно свяжитесь с администрацией магазина."
    )
    return _send_user_email(user, "Пароль успешно изменён", message)
