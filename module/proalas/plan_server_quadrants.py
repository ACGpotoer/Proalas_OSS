# -*- coding: utf-8 -*-
"""服务器域象限（黄/绿/蓝）：全局日历 + 设备 override（不含 AI 红区）。"""
from __future__ import annotations

from typing import Any

import module.config.server as server_mod
from module.proalas.calendar_schedule_resolver import resolve_global_day_from_calendar
from module.proalas.global_activity_calendar import load_global_calendar
from module.proalas.plan_schedule_store import get_device_day_override
from module.proalas.quadrant_policy import MERGE_PRIORITY, SERVER_QUADRANTS


def _merge_block(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not patch:
        return dict(base)
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            nested = dict(out[key])
            nested.update(value)
            out[key] = nested
        else:
            out[key] = value
    return out


def get_server_quadrants(
    device_id: str,
    date_str: str,
    *,
    server: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    物化/展示用：黄绿蓝来自服务器；设备 override 可覆盖同象限，但忽略 red。
    """
    srv = server or getattr(server_mod, 'server', 'cn')
    calendar = load_global_calendar()
    merged = resolve_global_day_from_calendar(calendar, date_str)

    override = get_device_day_override(device_id, date_str)
    for q in SERVER_QUADRANTS:
        block = override.get(q) if isinstance(override.get(q), dict) else {}
        if block:
            merged[q] = _merge_block(merged.get(q) or {}, block)

    return {q: dict(merged[q]) for q in MERGE_PRIORITY if isinstance(merged.get(q), dict) and merged[q]}


def get_red_quadrant(device_id: str, date_str: str, *, server: str | None = None) -> dict[str, Any]:
    """含全局 + 设备 override 的 red（供 AiPlanner）。"""
    from module.proalas.plan_quadrant_view import get_day_quadrants

    srv = server or getattr(server_mod, 'server', 'cn')
    quads = get_day_quadrants(device_id, date_str, server=srv)
    block = quads.get('red')
    return dict(block) if isinstance(block, dict) else {}
