"""ProalasAccount.ExpireAt 解析（只读 config，不写回）。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from proalas.alas_config import read_account_block


def _oss_disable_expiry() -> bool:
    """开源嵌入版默认不强制到期；设 PROALAS_ENFORCE_EXPIRY=1 可恢复商业逻辑。"""
    if os.environ.get("PROALAS_ENFORCE_EXPIRY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    flag = os.environ.get("PROALAS_OSS", "1").strip().lower()
    return flag in ("1", "true", "yes", "on", "")


def parse_expire_at(raw: Any) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    if hasattr(raw, "strftime"):
        return raw
    text = str(raw).strip()
    if not text or text == "—":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def account_expiry_context(config: dict[str, Any]) -> dict[str, Any]:
    """供登录页 / 账户卡片使用的到期状态。"""
    account = read_account_block(config)
    expire_raw = account.get("ExpireAt") or ""
    expire_at = parse_expire_at(expire_raw)
    if hasattr(expire_raw, "strftime"):
        expire_text = expire_raw.strftime("%Y-%m-%d %H:%M:%S")
    else:
        expire_text = str(expire_raw or "—")

    is_expired = False
    days_left: Optional[int] = None
    if expire_at is not None:
        now = datetime.now()
        is_expired = now > expire_at
        delta = (expire_at.date() - now.date()).days
        days_left = delta

    if _oss_disable_expiry():
        is_expired = False

    renewal_url = str(account.get("RenewalUrl") or "").strip()
    return {
        "expire_text": expire_text,
        "expire_at": expire_at,
        "is_expired": is_expired,
        "days_left": days_left,
        "renewal_url": renewal_url,
        "plan": str(account.get("PlanType") or "normal"),
    }


def device_is_expired(config_dir: str, device_id: str) -> bool:
    if _oss_disable_expiry():
        return False
    from proalas.alas_config import load_device_config

    cfg = load_device_config(config_dir, device_id)
    return bool(account_expiry_context(cfg).get("is_expired"))
