from flask import Blueprint, current_app, make_response, redirect, render_template, request, session, url_for

from proalas.account_expiry import account_expiry_context
from proalas.alas_config import load_device_config
from proalas.db import get_db
from proalas.device_cookie import DEVICE_COOKIE_NAME, sign_device_id
from proalas.models_devices import get_device, list_config_device_ids, password_needs_setup, sync_devices_from_config, verify_login

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        device_id = (request.form.get("device_id") or "").strip()
        password = request.form.get("password") or ""
        with get_db() as conn:
            sync_devices_from_config(conn, current_app.config["CONFIG_DIR"])
            if not verify_login(conn, device_id, password):
                return (
                    render_template(
                        "login.html",
                        error="设备号或密码错误",
                        devices=list_config_device_ids(current_app.config["CONFIG_DIR"]),
                        expired=False,
                        expiry=None,
                        device_id="",
                    ),
                    401,
                )
        cfg = load_device_config(current_app.config["CONFIG_DIR"], device_id)
        expiry = account_expiry_context(cfg)
        if expiry.get("is_expired"):
            return (
                render_template(
                    "login.html",
                    error="服务已过期，请联系管理员续费后重新登录。",
                    expired=True,
                    expiry=expiry,
                    device_id=device_id,
                    devices=list_config_device_ids(current_app.config["CONFIG_DIR"]),
                ),
                403,
            )
        session.clear()
        session["device_id"] = device_id
        with get_db() as conn:
            row = get_device(conn, device_id)
            session["needs_password_setup"] = password_needs_setup(row)
        session["account_expired"] = False
        # 远控 ticket 绑定：重新登录后旧链接立即失效
        from proalas.remote_control import ensure_session_bind

        ensure_session_bind(session)
        resp = make_response(redirect(url_for("main.app_home")))
        resp.set_cookie(
            DEVICE_COOKIE_NAME,
            sign_device_id(device_id, current_app.secret_key),
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return resp

    devices = list_config_device_ids(current_app.config["CONFIG_DIR"])
    return render_template(
        "login.html",
        devices=devices,
        error=None,
        expired=False,
        expiry=None,
        device_id="",
    )


@bp.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for("auth.login")))
    resp.delete_cookie(DEVICE_COOKIE_NAME, path="/")
    return resp
