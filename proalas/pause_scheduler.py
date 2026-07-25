"""每日暂停窗口后台检查（HostControl，与 QQ stop 同路径）。"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from proalas.alas_config import load_device_config, read_pause_schedule, save_pause_schedule
from proalas.host_pause import (
    apply_pause_until,
    format_hhmm,
    get_device_pause_status,
    parse_hhmm,
    window_end_datetime,
)
from proalas.models_devices import list_config_device_ids

logger = logging.getLogger(__name__)

_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _should_apply_daily(
    schedule: dict[str, Any],
    pause_status: dict[str, Any],
    now: datetime,
) -> tuple[bool, datetime | None]:
    if not schedule.get("daily_enabled"):
        return False, None
    start_min = parse_hhmm(str(schedule.get("start") or ""))
    end_min = parse_hhmm(str(schedule.get("end") or ""))
    if start_min is None or end_min is None:
        return False, None
    until = window_end_datetime(start_min, end_min, now)
    if until is None:
        return False, None
    if pause_status.get("active"):
        pause_until = str(pause_status.get("pause_until") or "")
        try:
            existing = datetime.strptime(pause_until, "%Y-%m-%d %H:%M:%S")
            if existing >= until - __import__("datetime").timedelta(minutes=1):
                return False, None
        except ValueError:
            pass
    last_date = str(schedule.get("last_applied_date") or "")
    today = now.strftime("%Y-%m-%d")
    if last_date == today and schedule.get("last_applied_end") == until.strftime("%H:%M"):
        return False, None
    return True, until


def _tick_once(app_config: dict[str, Any]) -> None:
    config_dir = app_config.get("CONFIG_DIR") or ""
    if not config_dir:
        return
    now = datetime.now()
    for device_id in list_config_device_ids(config_dir):
        cfg = load_device_config(config_dir, device_id)
        schedule = read_pause_schedule(cfg)
        if not schedule.get("daily_enabled"):
            continue
        pause_status = get_device_pause_status(app_config, device_id)
        ok_apply, until = _should_apply_daily(schedule, pause_status, now)
        if not ok_apply or until is None:
            continue
        start_min = parse_hhmm(str(schedule.get("start") or ""))
        end_min = parse_hhmm(str(schedule.get("end") or ""))
        success, msg = apply_pause_until(
            app_config,
            device_id,
            until,
            source="dap:daily",
            reason=f"dap:daily-{format_hhmm(start_min or 0)}-{format_hhmm(end_min or 0)}",
        )
        if success:
            save_pause_schedule(
                config_dir,
                device_id,
                daily_enabled=True,
                start=str(schedule.get("start") or ""),
                end=str(schedule.get("end") or ""),
                last_applied_date=now.strftime("%Y-%m-%d"),
                last_applied_end=until.strftime("%H:%M"),
            )
            logger.info("daily pause applied %s until %s", device_id, until)
        else:
            logger.warning("daily pause failed %s: %s", device_id, msg)


def _worker(app) -> None:
    while not _STOP.is_set():
        try:
            with app.app_context():
                _tick_once(dict(app.config))
        except Exception:
            logger.exception("pause scheduler tick failed")
        _STOP.wait(60.0)


def start_pause_scheduler(app) -> None:
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_worker, args=(app,), name="dap-pause-scheduler", daemon=True)
    _THREAD.start()
    logger.info("pause scheduler started (60s interval)")
