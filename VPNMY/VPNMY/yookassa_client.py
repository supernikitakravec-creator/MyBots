from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from yookassa import Configuration, Payment


@dataclass
class YooKassaConfig:
    shop_id: str
    secret_key: str
    return_url: str
    currency: str = "RUB"


class YooKassaClient:
    def __init__(self, cfg: YooKassaConfig) -> None:
        self.cfg = cfg
        Configuration.account_id = cfg.shop_id
        Configuration.secret_key = cfg.secret_key

    def create_payment(
        self,
        amount_rub: float,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        payload = {
            "amount": {"value": f"{amount_rub:.2f}", "currency": self.cfg.currency},
            "confirmation": {"type": "redirect", "return_url": self.cfg.return_url},
            "capture": True,
            "description": description[:127],
            "metadata": metadata or {},
        }
        payment = Payment.create(payload)
        confirmation_url = payment.confirmation.confirmation_url
        return confirmation_url, payment.id

    def get_status(self, payment_id: str) -> str:
        payment = Payment.find_one(payment_id)
        return payment.status


def load_yookassa_from_env() -> Optional[YooKassaClient]:
    shop_id = (os.getenv("YOOKASSA_SHOP_ID") or "").strip()
    secret_key = (os.getenv("YOOKASSA_SECRET_KEY") or "").strip()
    return_url = (os.getenv("YOOKASSA_RETURN_URL") or "").strip()
    currency = (os.getenv("YOOKASSA_CURRENCY") or "RUB").strip()
    if not (shop_id and secret_key and return_url):
        return None
    return YooKassaClient(YooKassaConfig(shop_id=shop_id, secret_key=secret_key, return_url=return_url, currency=currency))

