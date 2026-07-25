from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from proalas.alas_config import load_device_config, read_account_block, update_admin_account
from proalas.auth_util import admin_required
from proalas.db import get_db
from proalas.commands_store import delete_user_command_store
from proalas.models_devices import (
    admin_delete_device,
    admin_reset_password,
    admin_upsert_device,
    list_config_device_ids,
    list_devices,
    password_is_locked,
    sync_devices_from_config,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        from flask import current_app

        ok = False
        with get_db() as conn:
            row = conn.execute(
                "SELECT username, password_plain FROM admin_user WHERE username = ?",
                (u,),
            ).fetchone()
            if row and row["password_plain"] == p:
                ok = True
        if not ok and u == current_app.config["ADMIN_USERNAME"] and p == current_app.config["ADMIN_PASSWORD"]:
            ok = True
        if ok:
            session["admin_user"] = u
            return redirect(url_for("admin.device_list"))
        return render_template("admin/login.html", error="用户名或密码错误"), 401
    if session.get("admin_user"):
        return redirect(url_for("admin.device_list"))
    return render_template("admin/login.html", error=None)


@bp.route("/logout")
def admin_logout():
    session.pop("admin_user", None)
    return redirect(url_for("admin.admin_login"))


def _device_rows_with_account(conn, config_dir: str) -> list[dict]:
    sync_devices_from_config(conn, config_dir)
    rows = list_devices(conn)
    out = []
    plan_labels = {"normal": "Normal", "pro": "Pro", "pro_plus": "Pro+"}
    for r in rows:
        cfg = load_device_config(config_dir, r["device_id"])
        account = read_account_block(cfg)
        plan = str(account.get("PlanType") or "normal")
        expire_raw = account.get("ExpireAt") or ""
        if hasattr(expire_raw, "strftime"):
            expire_text = expire_raw.strftime("%Y-%m-%d %H:%M:%S")
        else:
            expire_text = str(expire_raw or "")
        out.append({
            "device_id": r["device_id"],
            "password_plain": r["password_plain"] or "",
            "password_locked": password_is_locked(r),
            "note": r["note"] or "",
            "plan": plan,
            "plan_text": plan_labels.get(plan, plan),
            "expire_at": expire_text,
            "renewal_url": str(account.get("RenewalUrl") or ""),
        })
    return out


@bp.route("/devices")
@admin_required
def device_list():
    config_dir = current_app.config["CONFIG_DIR"]
    with get_db() as conn:
        rows = _device_rows_with_account(conn, config_dir)
    return render_template(
        "admin/devices.html",
        devices=rows,
        config_devices=list_config_device_ids(config_dir),
    )


@bp.route("/devices/add", methods=["POST"])
@admin_required
def device_add():
    did = (request.form.get("device_id") or "").strip()
    pwd = request.form.get("password") or ""
    note = request.form.get("note") or ""
    if not did:
        return redirect(url_for("admin.device_list"))
    with get_db() as conn:
        admin_upsert_device(conn, did, pwd, note)
    return redirect(url_for("admin.device_list"))


@bp.route("/devices/<device_id>/edit", methods=["POST"])
@admin_required
def device_edit(device_id: str):
    note = request.form.get("note") or ""
    with get_db() as conn:
        row = conn.execute(
            "SELECT password_plain FROM device_account WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        pwd = row["password_plain"] if row else ""
        admin_upsert_device(conn, device_id, pwd, note)
    return redirect(url_for("admin.device_list"))


@bp.route("/devices/<device_id>/reset-password", methods=["POST"])
@admin_required
def device_reset_password(device_id: str):
    pwd = request.form.get("password") or ""
    with get_db() as conn:
        admin_reset_password(conn, device_id, pwd)
    return redirect(url_for("admin.device_list"))


@bp.route("/devices/<device_id>/account", methods=["POST"])
@admin_required
def device_update_account(device_id: str):
    plan = (request.form.get("plan_type") or "normal").strip().lower()
    if plan not in ("normal", "pro", "pro_plus"):
        plan = "normal"
    expire_at = (request.form.get("expire_at") or "").strip() or "2099-12-31 23:59:59"
    renewal_url = (request.form.get("renewal_url") or "").strip()
    update_admin_account(
        current_app.config["CONFIG_DIR"],
        device_id,
        plan_type=plan,
        expire_at=expire_at,
        renewal_url=renewal_url,
    )
    return redirect(url_for("admin.device_list"))


@bp.route("/devices/<device_id>/delete", methods=["POST"])
@admin_required
def device_delete(device_id: str):
    with get_db() as conn:
        admin_delete_device(conn, device_id)
    delete_user_command_store(current_app.config["COMMANDS_DIR"], device_id)
    return redirect(url_for("admin.device_list"))
