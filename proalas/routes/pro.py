from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, send_file, session

from proalas.account_expiry import account_expiry_context
from proalas.alas_config import (
    load_device_config,
    load_timetable_snapshot,
    proalas_data,
    read_account_block,
    read_ai_planner,
    read_game_resource,
    read_pause_schedule,
    save_pause_schedule,
)
from proalas.auth_util import login_required
from proalas.host_pause import (
    format_hhmm,
    get_device_pause_status,
    parse_hhmm,
    pause_for_hours,
    pause_for_today_window,
)
from proalas.device_screenshots import resolve_local_shot_path
from proalas.fleet_strength import fleet_strength_from_config
from proalas.game_resources import normalize_game_resource, resource_tiles
from proalas.proalas_scheduler import build_timer_plan_summary, list_proalas_schedulers
from proalas.remote_control import (
    ensure_session_bind,
    mmc_get_bytes,
    mmc_post_json,
    remote_status_payload,
    start_remote,
    stop_remote,
    validate_ticket_access,
)
from proalas.screen_monitor_panel import build_screen_monitor_context

# 最小合法 JPEG（黑点），画面未就绪时避免 <img> 破图
_REMOTE_PLACEHOLDER_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000"
    "ffdb004300080606070605080707070909080a0c141d0c0b0b0c1912130f"
    "141d1a1f1e1d1a1c1c20242e2720222c23281c1c2837292c30313434341f"
    "27393d32383c3432ffc0000b080001000101011100ffc4001f0000010501"
    "010101010100000000000000000102030405060708090a0bffc400b51000"
    "02010303020403050504040000017d010203000411051221314106135161"
    "07227114328191a1082342b1c11552d1f02433627282090a161718191a25"
    "262728292a3435363738393a434445464748494a535455565758595a6364"
    "65666768696a737475767778797a838485868788898a9293949596979899"
    "9aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3"
    "d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda00"
    "08010100003f00aa00ffd9"
)


def _remote_ticket_ok(ticket: str):
    return validate_ticket_access(
        dict(current_app.config),
        ticket,
        str(session.get("device_id") or ""),
        ensure_session_bind(session),
    )


bp = Blueprint("pro", __name__, url_prefix="/app/pro")


def _device_config() -> dict:
    cfg_dir = current_app.config["CONFIG_DIR"]
    device_id = session["device_id"]
    return load_device_config(cfg_dir, device_id)


@bp.get("/fleet-strength")
@login_required
def fleet_strength_partial():
    fleet = fleet_strength_from_config(_device_config())
    return render_template("partials/pro_fleet_strength.html", fleet=fleet)


@bp.get("/account")
@login_required
def account_partial():
    config = _device_config()
    account = read_account_block(config)
    planner = read_ai_planner(config)
    plan = str(account.get("PlanType") or "normal")
    plan_labels = {"normal": "Normal", "pro": "Pro", "pro_plus": "Pro+"}
    expire_raw = account.get("ExpireAt") or ""
    if hasattr(expire_raw, "strftime"):
        expire_text = expire_raw.strftime("%Y-%m-%d %H:%M:%S")
    else:
        expire_text = str(expire_raw or "—")
    renewal_url = str(account.get("RenewalUrl") or "").strip()
    expiry = account_expiry_context(config)
    return render_template(
        "partials/pro_account.html",
        device_id=session["device_id"],
        plan=plan,
        plan_text=plan_labels.get(plan, plan),
        expire_text=expire_text,
        renewal_url=renewal_url,
        strategy=planner["strategy"],
        planner_enabled=planner["scheduler_enable"],
        auto_apply=planner.get("auto_apply"),
        is_expired=expiry["is_expired"],
        days_left=expiry["days_left"],
    )


@bp.get("/runtime")
@login_required
def runtime_partial():
    data = proalas_data(_device_config())
    return render_template(
        "partials/pro_runtime.html",
        auto_break=data.get("AutoBreak") if isinstance(data.get("AutoBreak"), dict) else None,
        auto_equip=data.get("AutoEquip") if isinstance(data.get("AutoEquip"), dict) else None,
        exp_book=data.get("ExpBook") if isinstance(data.get("ExpBook"), dict) else None,
        collector_meta=data.get("CollectorMeta") if isinstance(data.get("CollectorMeta"), dict) else None,
    )


@bp.get("/scheduler")
@login_required
def scheduler_partial():
    rows = list_proalas_schedulers(_device_config())
    return render_template(
        "partials/pro_scheduler.html",
        rows=rows,
        device_id=session["device_id"],
    )


@bp.get("/timer-plan")
@login_required
def timer_plan_partial():
    device_id = session["device_id"]
    config = _device_config()
    tt_path = (current_app.config.get("TIMETABLE_PATH") or "").strip()
    snap = load_timetable_snapshot(tt_path, device_id) if tt_path else None
    summary = build_timer_plan_summary(config, timetable_snap=snap)
    return render_template(
        "partials/pro_timer_plan.html",
        summary=summary,
        device_id=device_id,
    )


@bp.get("/resources")
@login_required
def resources_partial():
    config = _device_config()
    dev = session["device_id"]
    gr = normalize_game_resource(read_game_resource(config))
    tiles = resource_tiles(gr)
    pdata = proalas_data(config)
    meta = pdata.get("CollectorMeta")
    if not isinstance(meta, dict):
        meta = {}
    return render_template(
        "partials/pro_resources.html",
        device_id=dev,
        gr=gr,
        tiles=tiles,
        collector_last_run=str(meta.get("lastRunAt") or ""),
    )


@bp.get("/screen-monitor")
@login_required
def screen_monitor_partial():
    device_id = session["device_id"]
    config = _device_config()
    ctx = build_screen_monitor_context(device_id, dict(current_app.config), config)
    return render_template("partials/pro_screen_monitor_inner.html", **ctx)


@bp.get("/pause-window")
@login_required
def pause_window_partial():
    device_id = session["device_id"]
    config = _device_config()
    schedule = read_pause_schedule(config)
    pause_status = get_device_pause_status(dict(current_app.config), device_id)
    return render_template(
        "partials/pro_pause_window.html",
        device_id=device_id,
        schedule=schedule,
        pause_status=pause_status,
    )


@bp.post("/pause/now")
@login_required
def pause_now():
    """立刻暂停（默认 5 小时）。"""
    body = request.get_json(silent=True) or {}
    try:
        hours = float(body.get("hours") or 5)
    except (TypeError, ValueError):
        hours = 5.0
    hours = max(0.5, min(hours, 72.0))
    device_id = session["device_id"]
    ok, msg = pause_for_hours(dict(current_app.config), device_id, hours=hours)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.post("/pause/today")
@login_required
def pause_today():
    body = request.get_json(silent=True) or {}
    start_min = parse_hhmm(str(body.get("start") or ""))
    end_min = parse_hhmm(str(body.get("end") or ""))
    if start_min is None or end_min is None:
        return jsonify({"ok": False, "error": "请先设置有效的时间段"}), 400
    device_id = session["device_id"]
    cfg_dir = current_app.config["CONFIG_DIR"]
    save_pause_schedule(
        cfg_dir,
        device_id,
        start=format_hhmm(start_min),
        end=format_hhmm(end_min),
    )
    ok, msg = pause_for_today_window(
        dict(current_app.config),
        device_id,
        start_min,
        end_min,
    )
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.post("/pause/daily")
@login_required
def pause_daily():
    body = request.get_json(silent=True) or {}
    start_min = parse_hhmm(str(body.get("start") or ""))
    end_min = parse_hhmm(str(body.get("end") or ""))
    if start_min is None or end_min is None:
        return jsonify({"ok": False, "error": "请先设置有效的时间段"}), 400
    device_id = session["device_id"]
    cfg_dir = current_app.config["CONFIG_DIR"]
    start_s = format_hhmm(start_min)
    end_s = format_hhmm(end_min)
    save_pause_schedule(
        cfg_dir,
        device_id,
        start=start_s,
        end=end_s,
        daily_enabled=True,
    )
    ok, msg = pause_for_today_window(
        dict(current_app.config),
        device_id,
        start_min,
        end_min,
    )
    if not ok and "今日所选时段已结束" in msg:
        return jsonify({
            "ok": True,
            "message": f"已保存每日暂停 {start_s}–{end_s}；今日时段已过，将于下次进入时段自动暂停",
        })
    return jsonify({"ok": ok, "message": msg if ok else f"已保存每日规则；{msg}"}), (200 if ok else 200)


@bp.post("/pause/daily/cancel")
@login_required
def pause_daily_cancel():
    device_id = session["device_id"]
    cfg_dir = current_app.config["CONFIG_DIR"]
    config = load_device_config(cfg_dir, device_id)
    schedule = read_pause_schedule(config)
    if not schedule.get("daily_enabled"):
        return jsonify({"ok": True, "message": "每日暂停未开启，无需取消"})
    save_pause_schedule(
        cfg_dir,
        device_id,
        start=str(schedule.get("start") or "22:00"),
        end=str(schedule.get("end") or "08:00"),
        daily_enabled=False,
    )
    return jsonify({
        "ok": True,
        "message": "已取消每日暂停；若当前仍在暂停中，请等到暂停结束，或联系管理员/QQ 群恢复运行",
    })


@bp.get("/screen-shot/<device_id>/<path:filename>")
@login_required
def screen_shot_file(device_id: str, filename: str):
    if device_id != session["device_id"]:
        abort(403)
    path = resolve_local_shot_path(device_id, filename, dict(current_app.config))
    if not path:
        abort(404)
    return send_file(path, mimetype="image/png", conditional=True)


@bp.get("/remote/status")
@login_required
def remote_status():
    device_id = session["device_id"]
    return jsonify(remote_status_payload(dict(current_app.config), device_id))


@bp.post("/remote/start")
@login_required
def remote_start():
    device_id = session["device_id"]
    bind = ensure_session_bind(session)
    ok, payload = start_remote(
        dict(current_app.config),
        device_id,
        session_bind=bind,
    )
    return jsonify(payload), (200 if ok else 400)


@bp.post("/remote/stop")
@login_required
def remote_stop_route():
    device_id = session["device_id"]
    body = request.get_json(silent=True) or {}
    ticket = str(body.get("ticket") or "")
    ok, payload = stop_remote(dict(current_app.config), device_id, ticket=ticket)
    return jsonify(payload), (200 if ok else 400)


@bp.get("/remote/view")
@login_required
def remote_view():
    from datetime import datetime

    ticket = str(request.args.get("ticket") or "").strip()
    meta = _remote_ticket_ok(ticket)
    if not meta:
        abort(403)
    left = max(0, int((meta["expires_at"] - datetime.now()).total_seconds()))
    return render_template(
        "remote_view.html",
        device_id=session["device_id"],
        ticket=ticket,
        expires_at=meta["expires_at"].strftime("%Y-%m-%d %H:%M:%S"),
        remaining_sec=left,
    )


@bp.get("/remote/frame")
@login_required
def remote_frame():
    ticket = str(request.args.get("ticket") or "").strip()
    if not _remote_ticket_ok(ticket):
        abort(403)
    ok, data, _err = mmc_get_bytes(
        dict(current_app.config),
        f"/mmc/remote/frame/{ticket}",
    )
    if not ok or not data:
        data = _REMOTE_PLACEHOLDER_JPEG
    return Response(
        data,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@bp.post("/remote/touch")
@login_required
def remote_touch():
    body = request.get_json(silent=True) or {}
    ticket = str(body.get("ticket") or "").strip()
    if not _remote_ticket_ok(ticket):
        abort(403)
    ok, data, err = mmc_post_json(
        dict(current_app.config),
        "/mmc/remote/touch",
        {
            "ticket": ticket,
            "x": int(body.get("x") or 0),
            "y": int(body.get("y") or 0),
            "action": str(body.get("action") or "down"),
        },
    )
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify(data)


@bp.post("/remote/text")
@login_required
def remote_text():
    body = request.get_json(silent=True) or {}
    ticket = str(body.get("ticket") or "").strip()
    if not _remote_ticket_ok(ticket):
        abort(403)
    ok, data, err = mmc_post_json(
        dict(current_app.config),
        "/mmc/remote/text",
        {
            "ticket": ticket,
            "text": str(body.get("text") or ""),
            "paste": bool(body.get("paste")),
        },
    )
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify(data)


@bp.post("/remote/key")
@login_required
def remote_key():
    body = request.get_json(silent=True) or {}
    ticket = str(body.get("ticket") or "").strip()
    if not _remote_ticket_ok(ticket):
        abort(403)
    ok, data, err = mmc_post_json(
        dict(current_app.config),
        "/mmc/remote/key",
        {
            "ticket": ticket,
            "name": str(body.get("name") or ""),
        },
    )
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify(data)

