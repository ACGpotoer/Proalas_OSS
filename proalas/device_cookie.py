"""与 Flask session 并行：ASGI /alas 代理读取同一登录设备（签名 Cookie）。"""
import os
from urllib.parse import unquote

from itsdangerous import URLSafeSerializer

DEVICE_COOKIE_NAME = "proalas_did"
_SALT = "proalas-device-v1"


def _secret() -> str:
    return os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


def sign_device_id(device_id: str, secret: str | None = None) -> str:
    secret = secret or _secret()
    return URLSafeSerializer(secret, salt=_SALT).dumps(device_id)


def unsign_device_id(token: str, secret: str | None = None) -> str | None:
    secret = secret or _secret()
    try:
        return URLSafeSerializer(secret, salt=_SALT).loads(token)
    except Exception:
        return None


def get_device_id_from_cookie_header(cookie_header: str | None, secret: str | None = None) -> str | None:
    if not cookie_header:
        return None
    secret = secret or _secret()
    for chunk in cookie_header.split(";"):
        chunk = chunk.strip()
        if not chunk.lower().startswith(DEVICE_COOKIE_NAME.lower() + "="):
            continue
        raw = chunk.split("=", 1)[1].strip()
        raw = unquote(raw)
        return unsign_device_id(raw, secret)
    return None
