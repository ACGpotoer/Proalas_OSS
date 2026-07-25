# -*- coding: utf-8 -*-
"""
计划表对外接口（当前仅 Python API；后续 AI 对接直接 import 本模块）。

action 建议值: run | pause | wake | sleep（宿主机 / 调度扩展用）
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from module.proalas.plan_schedule_store import (
    delete_entry as _delete_entry,
    get_entry as _get_entry,
    list_entries as _list_entries,
    list_entries_in_month as _list_entries_in_month,
    load_plan_file,
    upsert_device_day_override as _upsert_day_override,
    upsert_entry as _upsert_entry,
)
from module.proalas.calendar_schedule_resolver import resolve_matched_tags
from module.proalas.global_activity_calendar import load_global_calendar
from module.proalas.plan_quadrant_view import get_day_quadrants


def list_plan_entries(device_id: str) -> list[dict[str, Any]]:
    return _list_entries(device_id)


def get_plan_entry(device_id: str, entry_id: str) -> dict[str, Any] | None:
    return _get_entry(device_id, entry_id)


def upsert_plan_entry(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _upsert_entry(device_id, payload)


def delete_plan_entry(device_id: str, entry_id: str) -> bool:
    return _delete_entry(device_id, entry_id)


def get_plan_month_view(device_id: str, year: int, month: int) -> dict[str, Any]:
    """
    日历月视图数据（WebUI / AI 共用）。

    Returns:
        {
          year, month, monthLabel, weekdays,
          weeks: [[{date, inMonth, entries, quadrants, isToday}, ...]]
        }
    """
    import module.config.server as server_mod

    year, month = int(year), int(month)
    entries = _list_entries_in_month(device_id, year, month)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        d = str(e.get('date') or '')
        by_date.setdefault(d, []).append(e)

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    today = date.today()
    server = getattr(server_mod, 'server', 'cn')
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            key = d.isoformat()
            quadrants = {}
            matched_tags: list[dict[str, Any]] = []
            if d.month == month:
                quadrants = get_day_quadrants(device_id, key, server=server)
                matched_tags = resolve_matched_tags(load_global_calendar(), key)
            row.append({
                'date': key,
                'day': d.day,
                'inMonth': d.month == month,
                'isToday': d == today,
                'entries': by_date.get(key, []) if d.month == month else [],
                'quadrants': quadrants,
                'matchedTags': matched_tags,
            })
        weeks.append(row)

    return {
        'deviceId': str(device_id),
        'year': year,
        'month': month,
        'monthLabel': f'{year}年{month}月',
        'weekdays': ['一', '二', '三', '四', '五', '六', '日'],
        'weeks': weeks,
        'entryCount': len(entries),
    }


def get_matched_tags_for_date(date_str: str) -> list[dict[str, Any]]:
    """溯源：某日命中的 v3 schedule 列表。"""
    return resolve_matched_tags(load_global_calendar(), date_str)


def export_plan_api_spec() -> dict[str, Any]:
    """自描述接口清单，便于后续 AI Agent 读取。"""
    return {
        'module': 'module.proalas.plan_schedule_api',
        'storage': './config/proalas/PlanSchedule.json',
        'methods': [
            {'name': 'list_plan_entries', 'args': ['device_id']},
            {'name': 'get_plan_entry', 'args': ['device_id', 'entry_id']},
            {'name': 'upsert_plan_entry', 'args': ['device_id', 'payload']},
            {'name': 'delete_plan_entry', 'args': ['device_id', 'entry_id']},
            {'name': 'get_plan_month_view', 'args': ['device_id', 'year', 'month']},
            {'name': 'get_matched_tags_for_date', 'args': ['date_str']},
            {'name': 'upsert_device_day_override', 'args': ['device_id', 'date', 'payload', 'source']},
        ],
        'payloadSchema': {
            'date': 'YYYY-MM-DD',
            'start': 'HH:MM optional',
            'end': 'HH:MM optional',
            'action': 'run|pause|wake|sleep',
            'note': 'str',
            'source': 'manual|ai',
        },
        'quadrantSchema': {
            'yellow': 'daily tasks',
            'red': 'active / runtime (e.g. AI_planner)',
            'green': 'manual tasks',
            'blue': 'activity (campaign_events, scheduler_enable, gacha.up_ships)',
        },
        'whenSchema': {
            'weekday': '[1-7] ISO 周一=1；或 "all"',
            'monthday': '[1-31] 自然月离散日',
            'monthday_range': '[from, to] 自然月内连续日号；兼容 "4 to 25"',
            'range': '["YYYY-MM-DD", "YYYY-MM-DD"] 活动档期 ISO 闭区间',
            'legacy': 'day_type=every|list|to + day_in_week / list / to 别名',
        },
    }


def upsert_device_day_override(
    device_id: str,
    date_str: str,
    payload: dict[str, Any],
    *,
    source: str = 'manual',
) -> dict[str, Any]:
    return _upsert_day_override(device_id, date_str, payload, source=source)


def dump_plan_file() -> dict[str, Any]:
    return load_plan_file()
