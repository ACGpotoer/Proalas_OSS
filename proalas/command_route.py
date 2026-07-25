"""将 AI 解析结果分为：即时 Alas / 即时 UserData / 定时任务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from proalas.command_validate import (
    load_device_config,
    parse_change_tokens,
    resolve_special_command_name,
    validate_change_line,
)
from proalas.semantic_parse import format_userdata_line, parse_semantic_line
from proalas.semantic_translate import translate_semantic

_SCHEDULED_KIND: dict[str, str] = {
    "停止运行": "stop_time",
    "StopTime": "stop_time",
}

_IMMEDIATE_USERDATA = {
    "AutoAssembleTeamMain",
    "AutoAssembleTeamEvent",
    "AutoChouKa",
    "AutoBreakthrough",
    "AutoGetEXP",
    "AutoEventShop",
    "PlanEnabled",
    "PlanMode",
    "PlanSchedule",
    "AutoChouKaUsingRubik",
    "AutoChouKaPool",
    "AutoChouKaTimes",
    "AutoChouKaTime",
    "AutoGetEXPReserveBooks",
    "StarChoose",
    "AutoAssembleTeamMainRule",
    "AutoAssembleTeamMainTime",
    "AutoAssembleTeamEventRule",
    "AutoAssembleTeamEventTime",
    "EventShopBuyURShip",
    "EventShopUnlockSSR",
    "EventShopPresetFilter",
}

_SKIP_CPIA = {"AccountAnalysis", "账号分析"}


def route_commands_for_device(
    commands: list[str],
    *,
    device_id: str,
    config_dir: str,
) -> tuple[list[str], list[str], list[dict[str, Any]], list[tuple[str, str]]]:
    """
    返回:
      immediate_alas, immediate_userdata, pending_scheduled, rejected
    """
    immediate_alas: list[str] = []
    immediate_userdata: list[str] = []
    pending_scheduled: list[dict[str, Any]] = []
    rejected: list[tuple[str, str]] = []

    cfg: dict | None = None
    ts = datetime.now(timezone.utc).isoformat()

    queue: list[str] = [c.strip() for c in commands if c and c.strip()]
    while queue:
        line = queue.pop(0)

        sem = parse_semantic_line(line)
        if sem is not None:
            name, payload = sem
            tr = translate_semantic(device_id, name, payload)
            if tr.error:
                rejected.append((line, tr.error))
                continue
            pending_scheduled.extend(tr.scheduled)
            if tr.lines:
                queue = tr.lines + queue
            continue

        if line.lower().startswith("userdata "):
            parts = line.split()
            if len(parts) >= 4 and parts[1] == device_id:
                immediate_userdata.append(line)
            else:
                rejected.append((line, "userdata 行设备号不一致或格式错误"))
            continue

        if not line.lower().startswith("change "):
            rejected.append((line, "无法识别的指令格式"))
            continue

        tok = parse_change_tokens(line)
        if tok is None:
            rejected.append((line, "无法解析 change 行"))
            continue
        dev, path_or_name, val = tok
        if dev != device_id:
            rejected.append((line, f"设备号不一致: {dev}"))
            continue

        canon = resolve_special_command_name(path_or_name)
        if canon is not None:
            if canon in _SKIP_CPIA:
                rejected.append((line, "账号分析不进入 CPIA"))
                continue
            if canon == "StopTime":
                try:
                    payload = json.loads(val) if val.strip().startswith("[") else val
                except json.JSONDecodeError:
                    import ast

                    try:
                        payload = ast.literal_eval(val)
                    except (SyntaxError, ValueError):
                        payload = val
                if not isinstance(payload, list):
                    rejected.append((line, "StopTime 值须为数组"))
                    continue
                from proalas.stop_time_guard import stop_time_reject_reason

                reason = stop_time_reject_reason(payload)
                if reason:
                    rejected.append((line, reason))
                    continue
                pending_scheduled.append(
                    {
                        "kind": "stop_time",
                        "device_id": device_id,
                        "payload": payload,
                        "updated_at": ts,
                        "state": {},
                    }
                )
                continue
            if canon in _IMMEDIATE_USERDATA or canon not in _SCHEDULED_KIND:
                immediate_userdata.append(format_userdata_line(device_id, canon, val))
                continue

        if "." not in path_or_name:
            rejected.append((line, "非 Alas 路径且非已登记 UserData 字段"))
            continue

        if cfg is None:
            cfg = load_device_config(config_dir, device_id)
        good, err = validate_change_line(line, device_id, cfg)
        if good:
            immediate_alas.append(line)
        else:
            rejected.append((line, err or "校验未通过"))

    return immediate_alas, immediate_userdata, pending_scheduled, rejected
