"""HostControl 暂停：与 QQ Router / mmc-agent 同路径（pauseUntil）。"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"^(\d+)([hdm])$", re.I)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _default_host_control_path() -> str:
    # 开源版：优先 dap_data，其次 mumucontrol/runtime（若存在）
    root = os.environ.get("CONFIG_DIR", "")
    candidates = []
    if root:
        alas_root = os.path.dirname(os.path.abspath(root))
        candidates.append(os.path.join(alas_root, "dap_data", "HostControl.json"))
        candidates.append(
            os.path.join(alas_root, "mumucontrol", "runtime", "HostControl.json")
        )
    cwd = os.getcwd()
    candidates.append(os.path.join(cwd, "dap_data", "HostControl.json"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    # 默认写到 dap_data（无需 mmc）
    if root:
        return os.path.join(
            os.path.dirname(os.path.abspath(root)), "dap_data", "HostControl.json"
        )
    return os.path.join(cwd, "dap_data", "HostControl.json")


def host_control_path(config: dict[str, Any]) -> str:
    explicit = (config.get("HOST_CONTROL_PATH") or "").strip()
    if explicit:
        return explicit
    return _default_host_control_path()


def load_host_control(config: dict[str, Any]) -> dict[str, Any]:
    path = host_control_path(config)
    if not path or not os.path.isfile(path):
        return {"version": 1, "defaults": {}, "devices": {}, "pendingCommands": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            raw.setdefault("devices", {})
            return raw
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("read HostControl failed: %s", e)
    return {"version": 1, "defaults": {}, "devices": {}, "pendingCommands": []}


def save_host_control(config: dict[str, Any], data: dict[str, Any]) -> bool:
    path = host_control_path(config)
    if not path:
        return False
    data["updatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix=".hc.", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
    return None


def parse_hhmm(text: str) -> Optional[int]:
    m = _TIME_RE.match((text or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def format_hhmm(minutes: int) -> str:
    minutes = max(0, min(24 * 60 - 1, int(minutes)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_pause_active(row: dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    until = _parse_dt(row.get("pauseUntil"))
    if until is not None:
        return until > now
    return str(row.get("mode") or "") == "paused"


def get_device_pause_status(config: dict[str, Any], device_id: str) -> dict[str, Any]:
    hc = load_host_control(config)
    devices = hc.get("devices") or {}
    row = devices.get(device_id) if isinstance(devices, dict) else None
    if not isinstance(row, dict):
        row = {}
    until = _parse_dt(row.get("pauseUntil"))
    active = is_pause_active(row)
    return {
        "active": active,
        "pause_until": until.strftime("%Y-%m-%d %H:%M:%S") if until else "",
        "mode": str(row.get("mode") or "auto"),
        "last_action": str(row.get("lastAction") or ""),
        "host_control_configured": bool(host_control_path(config)),
    }


def _duration_text(delta: timedelta) -> str:
    total_min = max(1, int(delta.total_seconds() // 60))
    if total_min % 60 == 0 and total_min >= 60:
        return f"{total_min // 60}h"
    if total_min >= 60:
        return f"{total_min // 60}h{total_min % 60}m"
    return f"{total_min}m"


def apply_pause_until(
    config: dict[str, Any],
    device_id: str,
    until: datetime,
    *,
    source: str = "dap",
    reason: str = "",
) -> tuple[bool, str]:
    until = until.replace(microsecond=0)
    now = datetime.now().replace(microsecond=0)
    if until <= now:
        return False, "暂停结束时间必须晚于当前时间"
    hc = load_host_control(config)
    devices = hc.setdefault("devices", {})
    row = devices.setdefault(device_id, {})
    row["mode"] = "paused"
    row["pauseUntil"] = until.strftime("%Y-%m-%d %H:%M:%S")
    row["lastAction"] = reason or f"{source}:pause-until"
    row["updatedAt"] = now.strftime("%Y-%m-%d %H:%M:%S")
    if not save_host_control(config, hc):
        return False, "无法写入本地暂停文件（dap_data/HostControl.json）"
    duration = _duration_text(until - now)
    # 开源版默认不调 mmc；仅当显式配置了 MMC_COMMAND_URL 才尝试
    if not (config.get("MMC_COMMAND_URL") or "").strip():
        return True, f"已写入本地暂停至 {row['pauseUntil']}（无 mmc，仅预约）"
    mmc_ok, mmc_msg = _trigger_mmc_pause(config, device_id, duration, source=source)
    if mmc_ok:
        return True, f"已暂停至 {row['pauseUntil']}"
    return True, f"已暂停至 {row['pauseUntil']}（{mmc_msg}）"


def _trigger_mmc_pause(
    config: dict[str, Any],
    device_id: str,
    duration: str,
    *,
    source: str,
) -> tuple[bool, str]:
    url = (config.get("MMC_COMMAND_URL") or "").strip().rstrip("/")
    token = (config.get("MMC_COMMAND_TOKEN") or "").strip()
    if not url:
        return False, "未配置 MMC_COMMAND_URL"
    endpoint = url if url.endswith("/mmc/command") else f"{url}/mmc/command"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {
        "device": device_id,
        "verb": "pause",
        "duration": duration,
        "source": source,
        "trigger_tick": True,
    }
    try:
        resp = httpx.post(endpoint, json=body, headers=headers, timeout=45.0)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not data.get("ok"):
            err = str(data.get("error") or data.get("message") or resp.text)
            return False, err
        return True, str(data.get("message") or "mmc 已受理")
    except httpx.ConnectError as e:
        logger.warning("mmc pause unreachable %s: %s", endpoint, e)
        return False, "暂停服务暂时连不上，已记下请求；请稍后刷新或联系管理员"
    except Exception as e:
        logger.warning("mmc pause failed %s: %s", endpoint, e)
        return False, "暂停指令发送失败，请稍后重试或联系管理员"


def window_end_datetime(
    start_min: int,
    end_min: int,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """当前时刻若处于 [start,end] 窗口内，返回本段窗口结束时刻。"""
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    base = now.replace(second=0, microsecond=0)
    if start_min <= end_min:
        if start_min <= cur < end_min:
            h, m = divmod(end_min, 60)
            return base.replace(hour=h, minute=m)
        return None
    # 跨午夜：如 22:00–08:00
    if cur >= start_min:
        end_day = base + timedelta(days=1)
        h, m = divmod(end_min, 60)
        return end_day.replace(hour=h, minute=m)
    if cur < end_min:
        h, m = divmod(end_min, 60)
        return base.replace(hour=h, minute=m)
    return None


def window_contains(start_min: int, end_min: int, now: Optional[datetime] = None) -> bool:
    return window_end_datetime(start_min, end_min, now) is not None


def today_window_remaining_end(
    start_min: int,
    end_min: int,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """用于「当日暂停」：在窗口内则暂停到窗口末；窗口未开始则暂停到今日窗口末。"""
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    base = now.replace(second=0, microsecond=0)
    if start_min <= end_min:
        if cur >= end_min:
            return None
        h, m = divmod(end_min, 60)
        return base.replace(hour=h, minute=m)
    # 跨午夜
    if cur >= end_min and cur < start_min:
        return None
    end_dt = window_end_datetime(start_min, end_min, now)
    return end_dt


def pause_for_today_window(
    config: dict[str, Any],
    device_id: str,
    start_min: int,
    end_min: int,
) -> tuple[bool, str]:
    until = today_window_remaining_end(start_min, end_min)
    if until is None:
        start_s = format_hhmm(start_min)
        end_s = format_hhmm(end_min)
        if start_min > end_min:
            return (
                False,
                f"当前不在暂停时段内（每日 {start_s}–次日 {end_s} 为不运行时间）。"
                f"请在绿条时段内点击，或改用「每天该时段暂停」预约。",
            )
        return False, "今日所选时段已结束，请调整时间段或改用「每天该时段暂停」"
    return apply_pause_until(
        config,
        device_id,
        until,
        source="dap:today",
        reason=f"dap:today-{format_hhmm(start_min)}-{format_hhmm(end_min)}",
    )


def pause_for_hours(
    config: dict[str, Any],
    device_id: str,
    hours: float = 5.0,
) -> tuple[bool, str]:
    """立刻暂停指定小时数（默认 5 小时）。"""
    hours = max(0.1, float(hours))
    until = datetime.now().replace(microsecond=0) + timedelta(hours=hours)
    return apply_pause_until(
        config,
        device_id,
        until,
        source="dap:now",
        reason=f"dap:now-{hours:g}h",
    )
