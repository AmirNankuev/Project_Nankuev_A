from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache


class CdekApiError(Exception):
    """Ошибка при обращении к API СДЭК."""


class CdekClient:
    """Минимальный клиент СДЭК API v2 для учебного интернет-магазина.

    В режиме CDEK_DEMO_MODE=True сетевые запросы не выполняются: возвращаются
    демонстрационные данные, чтобы проект запускался без договора и ключей СДЭК.
    Для реального контура нужно задать CDEK_DEMO_MODE=false и заполнить ключи.
    """

    TOKEN_CACHE_KEY = "cdek_access_token"

    def __init__(self) -> None:
        self.base_url = settings.CDEK_BASE_URL.rstrip("/")
        self.client_id = settings.CDEK_CLIENT_ID
        self.client_secret = settings.CDEK_CLIENT_SECRET
        self.demo_mode = settings.CDEK_DEMO_MODE
        self.timeout = settings.CDEK_REQUEST_TIMEOUT

    def _require_credentials(self) -> None:
        if not self.client_id or not self.client_secret:
            raise CdekApiError(
                "Не заданы CDEK_CLIENT_ID и CDEK_CLIENT_SECRET. "
                "Заполните переменные окружения или включите CDEK_DEMO_MODE=true."
            )

    def get_token(self) -> str:
        if self.demo_mode:
            return "demo-token"

        self._require_credentials()
        cached_token = cache.get(self.TOKEN_CACHE_KEY)
        if cached_token:
            return cached_token

        response = requests.post(
            f"{self.base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise CdekApiError(f"Ошибка авторизации СДЭК: {response.text}")

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise CdekApiError(f"СДЭК не вернул access_token: {payload}")

        expires_in = int(payload.get("expires_in", 3600))
        cache.set(self.TOKEN_CACHE_KEY, token, max(expires_in - 60, 60))
        return token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json",
        }

    def calculate_tariff(
        self,
        *,
        to_city_code: int,
        delivery_type: str,
        weight: int,
        tariff_code: int | None = None,
    ) -> dict[str, Any]:
        tariff_code = tariff_code or self._tariff_by_delivery_type(delivery_type)
        weight = max(int(weight), settings.CDEK_DEFAULT_WEIGHT_GRAMS)

        if self.demo_mode:
            # [Смоделировано] Учебная формула: базовая цена + надбавка за вес.
            # Нужна только для локального запуска без ключей СДЭК.
            delivery_sum = Decimal("350.00") + Decimal(max(weight - 300, 0)) / Decimal("1000") * Decimal("120.00")
            return {
                "delivery_sum": delivery_sum.quantize(Decimal("0.01")),
                "period_min": 2,
                "period_max": 5,
                "tariff_code": tariff_code,
                "raw": {"demo": True, "to_city_code": to_city_code, "weight": weight},
            }

        payload = {
            "type": 1,
            "tariff_code": tariff_code,
            "from_location": {"code": settings.CDEK_FROM_CITY_CODE},
            "to_location": {"code": int(to_city_code)},
            "packages": [
                {
                    "weight": weight,
                    "length": settings.CDEK_DEFAULT_PACKAGE_LENGTH_CM,
                    "width": settings.CDEK_DEFAULT_PACKAGE_WIDTH_CM,
                    "height": settings.CDEK_DEFAULT_PACKAGE_HEIGHT_CM,
                }
            ],
        }

        response = requests.post(
            f"{self.base_url}/calculator/tariff",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise CdekApiError(f"Ошибка расчёта доставки СДЭК: {response.text}")

        payload = response.json()
        return {
            "delivery_sum": Decimal(str(payload.get("delivery_sum", "0.00"))),
            "period_min": payload.get("period_min"),
            "period_max": payload.get("period_max"),
            "tariff_code": tariff_code,
            "raw": payload,
        }

    def create_order(
        self,
        *,
        order,
        recipient: dict[str, str],
        to_city_code: int,
        delivery_type: str,
        weight: int,
        tariff_code: int | None = None,
    ) -> dict[str, Any]:
        tariff_code = tariff_code or self._tariff_by_delivery_type(delivery_type)
        items = []
        for order_item in order.items.select_related("product_variant__product"):
            product = order_item.product_variant.product
            items.append(
                {
                    "name": product.name[:255],
                    "ware_key": product.article[:50],
                    "payment": {"value": 0},
                    "cost": float(order_item.unit_price),
                    "weight": settings.CDEK_DEFAULT_WEIGHT_GRAMS,
                    "amount": order_item.quantity,
                }
            )

        if self.demo_mode:
            return {
                "entity": {
                    "uuid": f"DEMO-{order.order_number}",
                },
                "requests": [],
                "demo": True,
            }

        payload = {
            "type": 1,
            "number": order.order_number,
            "tariff_code": tariff_code,
            "from_location": {"code": settings.CDEK_FROM_CITY_CODE},
            "to_location": {
                "code": int(to_city_code),
                "address": recipient["address"],
            },
            "recipient": {
                "name": recipient["name"],
                "phones": [{"number": recipient["phone"]}],
                "email": recipient["email"],
            },
            "packages": [
                {
                    "number": "1",
                    "weight": max(int(weight), settings.CDEK_DEFAULT_WEIGHT_GRAMS),
                    "length": settings.CDEK_DEFAULT_PACKAGE_LENGTH_CM,
                    "width": settings.CDEK_DEFAULT_PACKAGE_WIDTH_CM,
                    "height": settings.CDEK_DEFAULT_PACKAGE_HEIGHT_CM,
                    "items": items,
                }
            ],
        }

        response = requests.post(
            f"{self.base_url}/orders",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise CdekApiError(f"Ошибка создания заказа СДЭК: {response.text}")

        return response.json()

    @staticmethod
    def _tariff_by_delivery_type(delivery_type: str) -> int:
        # 137 — склад-дверь, 136 — склад-склад. Значения можно заменить в настройках.
        if delivery_type == "cdek_pickup":
            return 136
        return settings.CDEK_DEFAULT_TARIFF_CODE
