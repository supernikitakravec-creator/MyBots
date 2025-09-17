from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


class HiddifyAPIError(Exception):
    pass


@dataclass
class HiddifyConfig:
    base_url: str
    api_token: str
    create_user_path: str
    get_user_path: str
    get_subscription_path: str
    auth_style: str  # BEARER or X_API_KEY
    subscription_url_template: Optional[str] = None


def build_headers(api_token: str, auth_style: str) -> Dict[str, str]:
    if auth_style.upper() == "X_API_KEY":
        return {
            "X-API-KEY": api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    # Default: Bearer
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def days_for_months(months: int) -> int:
    # Conservative mapping to days; you can adjust if your panel supports month granularity
    if months == 1:
        return 30
    if months == 3:
        return 90
    if months == 6:
        return 180
    if months == 12:
        return 365
    return months * 30


class HiddifyPanelClient:
    def __init__(self, cfg: HiddifyConfig) -> None:
        self.cfg = cfg

    def create_or_extend_user(
        self,
        username: str,
        months: int,
        note: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Creates (or upserts) a user and returns (subscription_url, raw_response).

        This implementation targets common Hiddify/Panel APIs. If your version differs,
        adjust env paths or set SUBSCRIPTION_URL_TEMPLATE.
        """
        base = self.cfg.base_url.rstrip("/")
        headers = build_headers(self.cfg.api_token, self.cfg.auth_style)
        create_url = base + self.cfg.create_user_path

        payload: Dict[str, Any] = {
            "username": username,
            "expire_days": days_for_months(months),
            "enable": True,
        }
        if note:
            payload["note"] = note

        resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=20)
        if resp.status_code >= 400:
            raise HiddifyAPIError(f"Create user failed: {resp.status_code} {resp.text}")

        data = resp.json() if resp.content else {}

        # Try to obtain subscription link from response
        subscription_url = (
            data.get("subscription_url")
            or data.get("sub_url")
            or (data.get("data") or {}).get("subscription_url")
            or (data.get("data") or {}).get("sub_url")
        )

        user_id = data.get("id") or (data.get("data") or {}).get("id")
        user_uuid = data.get("uuid") or (data.get("data") or {}).get("uuid")

        # If not present, try GET subscription endpoint
        if not subscription_url:
            if self.cfg.subscription_url_template and (user_uuid or user_id):
                subscription_url = self.cfg.subscription_url_template.format(
                    base_url=base, user_id=user_id or "", uuid=user_uuid or ""
                )
            elif user_id:
                get_sub_url = base + self.cfg.get_subscription_path.format(user_id=user_id)
                sub_resp = requests.get(get_sub_url, headers=headers, timeout=20)
                if sub_resp.status_code < 400:
                    sub_data = sub_resp.json() if sub_resp.content else {}
                    subscription_url = (
                        sub_data.get("subscription_url")
                        or sub_data.get("sub_url")
                        or (sub_data.get("data") or {}).get("subscription_url")
                        or (sub_data.get("data") or {}).get("sub_url")
                    )

        if not subscription_url:
            raise HiddifyAPIError(
                "Could not retrieve subscription URL. Configure SUBSCRIPTION_URL_TEMPLATE or API paths."
            )

        return subscription_url, data


def load_hiddify_clients_from_env() -> Dict[str, HiddifyPanelClient]:
    base_paths = {
        "create": os.getenv("HIDDIFY_API_CREATE_USER_PATH", "/api/v1/users"),
        "get_user": os.getenv("HIDDIFY_API_GET_USER_PATH", "/api/v1/users/{user_id}"),
        "get_sub": os.getenv("HIDDIFY_API_GET_SUBSCRIPTION_PATH", "/api/v1/users/{user_id}/subscription"),
    }
    auth_style = os.getenv("HIDDIFY_API_AUTH_STYLE", "BEARER")
    sub_template = os.getenv("SUBSCRIPTION_URL_TEMPLATE") or None

    def mk(name_prefix: str) -> Optional[HiddifyPanelClient]:
        base_url = os.getenv(f"HIDDIFY_{name_prefix}_BASE_URL", "").strip()
        api_token = os.getenv(f"HIDDIFY_{name_prefix}_API_TOKEN", "").strip()
        if not base_url or not api_token:
            return None
        cfg = HiddifyConfig(
            base_url=base_url,
            api_token=api_token,
            create_user_path=base_paths["create"],
            get_user_path=base_paths["get_user"],
            get_subscription_path=base_paths["get_sub"],
            auth_style=auth_style,
            subscription_url_template=sub_template,
        )
        return HiddifyPanelClient(cfg)

    clients: Dict[str, HiddifyPanelClient] = {}
    tr = mk("TR")
    if tr:
        clients["TR"] = tr
    nl = mk("NL")
    if nl:
        clients["NL"] = nl
    return clients

