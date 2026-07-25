"""读写 Alas config/{device_id}.json（ProAlas 数据与 Scheduler）。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


def device_config_path(config_dir: str, device_id: str) -> Path:
    return Path(config_dir).resolve() / f"{device_id}.json"


def load_device_config(config_dir: str, device_id: str) -> dict[str, Any]:
    path = device_config_path(config_dir, device_id)
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_device_config(config_dir: str, device_id: str, data: dict[str, Any]) -> None:
    path = device_config_path(config_dir, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".json",
        prefix=f".{device_id}.",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def deep_get(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def deep_set(data: dict[str, Any], keys: list[str], value: Any) -> None:
    cur = data
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def proalas_data(config: dict[str, Any]) -> dict[str, Any]:
    block = config.get("ProalasData")
    return block if isinstance(block, dict) else {}


def read_game_resource(config: dict[str, Any]) -> dict[str, Any]:
    gr = proalas_data(config).get("GameResource")
    return gr if isinstance(gr, dict) else {}


def read_fleet_strength(config: dict[str, Any]) -> dict[str, Any]:
    fs = proalas_data(config).get("FleetStrength")
    return fs if isinstance(fs, dict) else {}


def read_pause_schedule(config: dict[str, Any]) -> dict[str, Any]:
    block = proalas_data(config).get("PauseSchedule")
    if not isinstance(block, dict):
        block = {}
    return {
        "start": str(block.get("Start") or "22:00"),
        "end": str(block.get("End") or "08:00"),
        "daily_enabled": bool(block.get("DailyEnabled")),
        "last_applied_date": str(block.get("LastAppliedDate") or ""),
        "last_applied_end": str(block.get("LastAppliedEnd") or ""),
    }


def save_pause_schedule(
    config_dir: str,
    device_id: str,
    *,
    start: str,
    end: str,
    daily_enabled: bool | None = None,
    last_applied_date: str = "",
    last_applied_end: str = "",
) -> None:
    data = load_device_config(config_dir, device_id)
    if "ProalasData" not in data or not isinstance(data["ProalasData"], dict):
        data["ProalasData"] = {}
    pd = data["ProalasData"]
    if not isinstance(pd.get("PauseSchedule"), dict):
        pd["PauseSchedule"] = {}
    sched = pd["PauseSchedule"]
    sched["Start"] = start
    sched["End"] = end
    if daily_enabled is not None:
        sched["DailyEnabled"] = bool(daily_enabled)
        if not daily_enabled:
            sched.pop("LastAppliedDate", None)
            sched.pop("LastAppliedEnd", None)
    if last_applied_date:
        sched["LastAppliedDate"] = last_applied_date
    if last_applied_end:
        sched["LastAppliedEnd"] = last_applied_end
    save_device_config(config_dir, device_id, data)


def update_admin_account(
    config_dir: str,
    device_id: str,
    *,
    plan_type: str,
    expire_at: str,
    renewal_url: str = "",
) -> None:
    data = load_device_config(config_dir, device_id)
    if "ProalasAccount" not in data or not isinstance(data["ProalasAccount"], dict):
        data["ProalasAccount"] = {"Scheduler": {}, "ProalasAccount": {}}
    acc_wrap = data["ProalasAccount"]
    if not isinstance(acc_wrap.get("ProalasAccount"), dict):
        acc_wrap["ProalasAccount"] = {}
    acc = acc_wrap["ProalasAccount"]
    acc["PlanType"] = plan_type
    acc["ExpireAt"] = expire_at
    if renewal_url:
        acc["RenewalUrl"] = renewal_url
    save_device_config(config_dir, device_id, data)


def read_account_block(config: dict[str, Any]) -> dict[str, Any]:
    block = deep_get(config, ["ProalasAccount", "ProalasAccount"], {})
    return block if isinstance(block, dict) else {}


def read_ai_planner(config: dict[str, Any]) -> dict[str, Any]:
    sched = deep_get(config, ["ProalasAiPlanner", "Scheduler"], {})
    body = deep_get(config, ["ProalasAiPlanner", "ProalasAiPlanner"], {})
    if not isinstance(sched, dict):
        sched = {}
    if not isinstance(body, dict):
        body = {}
    return {
        "strategy": str(body.get("Strategy") or "conservative"),
        "auto_apply": bool(body.get("AutoApply")),
        "scheduler_enable": bool(sched.get("Enable")),
        "next_run": str(sched.get("NextRun") or ""),
    }


def set_ai_planner_strategy(
    config_dir: str,
    device_id: str,
    mode: str,
    *,
    enable: bool = True,
) -> None:
    data = load_device_config(config_dir, device_id)
    if "ProalasAiPlanner" not in data or not isinstance(data["ProalasAiPlanner"], dict):
        data["ProalasAiPlanner"] = {}
    planner = data["ProalasAiPlanner"]
    if not isinstance(planner.get("ProalasAiPlanner"), dict):
        planner["ProalasAiPlanner"] = {}
    if not isinstance(planner.get("Scheduler"), dict):
        planner["Scheduler"] = {}
    planner["ProalasAiPlanner"]["Strategy"] = mode
    planner["Scheduler"]["Enable"] = bool(enable)
    save_device_config(config_dir, device_id, data)


def load_timetable_snapshot(
    timetable_path: str,
    device_id: str,
) -> Optional[dict[str, Any]]:
    path = Path(timetable_path)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    devices = raw.get("devices")
    if not isinstance(devices, dict):
        return None
    snap = devices.get(device_id)
    return snap if isinstance(snap, dict) else None
