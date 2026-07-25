"""登录鉴权：设备 session + 账户到期拦截。"""
from functools import wraps

from flask import current_app, redirect, render_template, session, url_for


def _device_expiry(device_id: str) -> dict:
    from proalas.account_expiry import account_expiry_context
    from proalas.alas_config import load_device_config

    cfg = load_device_config(current_app.config["CONFIG_DIR"], device_id)
    return account_expiry_context(cfg)


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        device_id = session.get("device_id")
        if not device_id:
            return redirect(url_for("auth.login"))
        expiry = _device_expiry(device_id)
        if expiry.get("is_expired"):
            session.clear()
            return render_template(
                "login.html",
                error="服务已过期，请联系管理员续费后重新登录。",
                expired=True,
                expiry=expiry,
                device_id=device_id,
                devices=[],
            ), 403
        return f(*args, **kwargs)

    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin_user"):
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)

    return wrapped
