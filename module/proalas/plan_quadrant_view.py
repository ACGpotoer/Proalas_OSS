# -*- coding: utf-8 -*-
"""合并全局日历 + 设备 override，生成某日四色象限视图。"""
from __future__ import annotations

from typing import Any

from module.proalas.global_activity_calendar import (
    QUADRANT_KEYS,
    get_global_day,
    resolve_manifest_blue,
)
from module.proalas.plan_schedule_store import get_device_day_override


def _merge_block(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if not override:
        return dict(base)
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            nested = dict(out[key])
            nested.update(value)
            out[key] = nested
        else:
            out[key] = value
    return out


def get_day_quadrants(
    device_id: str,
    date_str: str,
    *,
    server: str = 'cn',
    allow_manifest_fallback: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Returns:
        { yellow: {...}, red: {...}, green: {...}, blue: {...} }
    """
    global_day = get_global_day(date_str)
    # get_global_day v3 返回 {quadrant: block}；v2 legacy 同结构
    device_override = get_device_day_override(device_id, date_str)
    merged: dict[str, dict[str, Any]] = {}
    for key in QUADRANT_KEYS:
        if isinstance(global_day.get(key), dict):
            base = global_day[key]
        else:
            base = global_day.get(key) if isinstance(global_day.get(key), dict) else {}
        over = device_override.get(key) if isinstance(device_override.get(key), dict) else {}
        block = _merge_block(base, over)
        if block:
            merged[key] = block

    if allow_manifest_fallback and not merged.get('blue'):
        manifest_blue = resolve_manifest_blue(server)
        if manifest_blue:
            merged['blue'] = manifest_blue
    return merged


def get_blue_payload(
    device_id: str,
    date_str: str,
    *,
    server: str = 'cn',
    allow_manifest_fallback: bool = True,
) -> dict[str, Any]:
    return get_day_quadrants(
        device_id,
        date_str,
        server=server,
        allow_manifest_fallback=allow_manifest_fallback,
    ).get('blue') or {}
