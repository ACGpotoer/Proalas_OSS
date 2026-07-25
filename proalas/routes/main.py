from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from proalas.account_expiry import account_expiry_context
from proalas.alas_config import (
    load_device_config,
    load_timetable_snapshot,
    proalas_data,
    read_game_resource,
    read_pause_schedule,
)
from proalas.auth_util import login_required
from proalas.db import get_db
from proalas.fleet_strength import fleet_strength_from_config
from proalas.game_resources import normalize_game_resource, resource_tiles
from proalas.host_pause import get_device_pause_status
from proalas.models_devices import get_device, password_is_locked, password_needs_setup, set_password_once
from proalas.proalas_scheduler import build_timer_plan_summary, list_proalas_schedulers
from proalas.screen_monitor_panel import build_screen_monitor_context

bp = Blueprint("main", __name__)


@bp.get("/app/pane/pro")
@login_required
def pane_pro():
    """首屏服务端渲染各卡片，避免嵌套 hx-trigger=load 偶发不触发导致空白。"""
    device_id = session["device_id"]
    config = load_device_config(current_app.config["CONFIG_DIR"], device_id)
    app_cfg = dict(current_app.config)
    screen_monitor = build_screen_monitor_context(device_id, app_cfg, config)

    schedule = read_pause_schedule(config)
    pause_status = get_device_pause_status(app_cfg, device_id)

    gr = normalize_game_resource(read_game_resource(config))
    tiles = resource_tiles(gr)
    pdata = proalas_data(config)
    meta = pdata.get("CollectorMeta")
    if not isinstance(meta, dict):
        meta = {}

    fleet = fleet_strength_from_config(config)

    tt_path = (current_app.config.get("TIMETABLE_PATH") or "").strip()
    snap = load_timetable_snapshot(tt_path, device_id) if tt_path else None
    timer_summary = build_timer_plan_summary(config, timetable_snap=snap)

    return render_template(
        "partials/pane_pro.html",
        **screen_monitor,
        schedule=schedule,
        pause_status=pause_status,
        gr=gr,
        tiles=tiles,
        collector_last_run=str(meta.get("lastRunAt") or ""),
        fleet=fleet,
        auto_break=pdata.get("AutoBreak") if isinstance(pdata.get("AutoBreak"), dict) else None,
        auto_equip=pdata.get("AutoEquip") if isinstance(pdata.get("AutoEquip"), dict) else None,
        exp_book=pdata.get("ExpBook") if isinstance(pdata.get("ExpBook"), dict) else None,
        collector_meta=meta or None,
        rows=list_proalas_schedulers(config),
        summary=timer_summary,
    )


@bp.get("/app/pane/original")
@login_required
def pane_original():
    return render_template("partials/pane_original.html", device_id=session["device_id"])


@bp.route("/")
def index():
    if session.get("device_id"):
        return redirect(url_for("main.app_home"))
    return redirect(url_for("auth.login"))


@bp.route("/app")
@login_required
def app_home():
    from proalas.announcement import load_announcement

    ann = load_announcement()
    device_id = session["device_id"]
    cfg = load_device_config(current_app.config["CONFIG_DIR"], device_id)
    expiry = account_expiry_context(cfg)
    session["account_expired"] = bool(expiry.get("is_expired"))
    pwd_ok = request.args.get("pwd_ok") == "1"
    pwd_err = request.args.get("pwd_err") or ""
    with get_db() as conn:
        row = get_device(conn, device_id)
        needs_password_setup = password_needs_setup(row) if row else False
        password_locked = password_is_locked(row) if row else False
    session["needs_password_setup"] = needs_password_setup
    return render_template(
        "main.html",
        device_id=device_id,
        announcement=ann,
        pane_pro_url=url_for("main.pane_pro"),
        pane_original_url=url_for("main.pane_original"),
        expiry=expiry,
        pwd_ok=pwd_ok,
        pwd_err=pwd_err,
        needs_password_setup=needs_password_setup,
        password_locked=password_locked,
    )


@bp.route("/app/password", methods=["POST"])
@login_required
def change_password():
    new_pwd = (request.form.get("new_password") or "").strip()
    confirm_pwd = (request.form.get("confirm_password") or "").strip()
    if new_pwd != confirm_pwd:
        return redirect(url_for("main.app_home", pwd_err="mismatch"))
    with get_db() as conn:
        ok, err = set_password_once(conn, session["device_id"], new_pwd)
    if not ok:
        code = "locked" if "不可修改" in err else "short"
        if err == "密码至少 4 位":
            code = "short"
        elif "不可修改" in err:
            code = "locked"
        else:
            code = "fail"
        return redirect(url_for("main.app_home", pwd_err=code))
    session["needs_password_setup"] = False
    return redirect(url_for("main.app_home", pwd_ok="1"))
