from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import requests
from django.conf import settings
from django.urls import reverse
from requests.auth import HTTPBasicAuth


class YooKassaApiError(Exception):
    """Ошибка интеграции с ЮKassa."""


def _money_value(amount):
    value = Decimal(str(amount or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


class YooKassaClient:
    def __init__(self, request=None):
        self.request = request
        self.api_url = settings.YOOKASSA_API_URL.rstrip("/")
        self.shop_id = settings.YOOKASSA_SHOP_ID
        self.secret_key = settings.YOOKASSA_SECRET_KEY
        self.demo_mode = settings.YOOKASSA_DEMO_MODE

    def _return_url(self, order):
        path = reverse("checkout_payment", kwargs={"order_number": order.order_number})
        if self.request is not None:
            return self.request.build_absolute_uri(path)
        return f"{settings.YOOKASSA_RETURN_BASE_URL.rstrip('/')}{path}"

    def _auth(self):
        if not self.shop_id or not self.secret_key:
            raise YooKassaApiError("Не заданы YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY.")
        return HTTPBasicAuth(self.shop_id, self.secret_key)

    def create_payment(self, order):
        if self.demo_mode:
            payment_id = f"demo_{order.order_number.lower()}_{uuid4().hex[:8]}"
            confirmation_url = f"{self._return_url(order)}?demo=1"
            return {
                "id": payment_id,
                "status": "pending",
                "paid": False,
                "confirmation_url": confirmation_url,
                "raw": {
                    "id": payment_id,
                    "status": "pending",
                    "paid": False,
                    "demo": True,
                    "confirmation": {
                        "type": "redirect",
                        "confirmation_url": confirmation_url,
                    },
                },
            }

        payload = {
            "amount": {
                "value": _money_value(order.total_amount),
                "currency": settings.YOOKASSA_CURRENCY,
            },
            "capture": bool(settings.YOOKASSA_CAPTURE),
            "confirmation": {
                "type": "redirect",
                "return_url": self._return_url(order),
            },
            "description": f"Оплата заказа {order.order_number}",
            "metadata": {
                "order_id": str(order.id),
                "order_number": order.order_number,
            },
        }

        response = requests.post(
            f"{self.api_url}/payments",
            json=payload,
            auth=self._auth(),
            headers={"Idempotence-Key": str(uuid4())},
            timeout=settings.YOOKASSA_REQUEST_TIMEOUT,
        )

        if response.status_code >= 400:
            raise YooKassaApiError(f"Ошибка создания платежа ЮKassa: {response.text}")

        return self._normalize_payment(response.json())

    def get_payment(self, payment_id):
        if not payment_id:
            raise YooKassaApiError("У заказа нет идентификатора платежа ЮKassa.")

        if self.demo_mode and str(payment_id).startswith("demo_"):
            return {
                "id": payment_id,
                "status": "pending",
                "paid": False,
                "confirmation_url": "",
                "raw": {
                    "id": payment_id,
                    "status": "pending",
                    "paid": False,
                    "demo": True,
                },
            }

        response = requests.get(
            f"{self.api_url}/payments/{payment_id}",
            auth=self._auth(),
            timeout=settings.YOOKASSA_REQUEST_TIMEOUT,
        )

        if response.status_code >= 400:
            raise YooKassaApiError(f"Ошибка проверки платежа ЮKassa: {response.text}")

        return self._normalize_payment(response.json())

    @staticmethod
    def _normalize_payment(payload):
        confirmation = payload.get("confirmation") or {}
        return {
            "id": payload.get("id"),
            "status": payload.get("status"),
            "paid": bool(payload.get("paid")),
            "confirmation_url": confirmation.get("confirmation_url") or "",
            "raw": payload,
        }


def payment_is_successful(payment_payload):
    return bool(payment_payload.get("paid")) or payment_payload.get("status") == "succeeded"


def payment_is_failed(payment_payload):
    return payment_payload.get("status") in {"canceled"}
