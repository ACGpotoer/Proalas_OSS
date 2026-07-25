# -*- coding: utf-8 -*-
"""v3 全局日历：tags + schedules → 某日四色象限（兼容 v2 days 逐日格式）。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

QUADRANT_KEYS = ('yellow', 'red', 'green', 'blue')

# ISO：周一=1 … 周日=7
_WEEKDAY_ALL = (1, 2, 3, 4, 5, 6, 7)


def _parse_iso_date(text: str) -> Optional[date]:
    text = str(text or '').strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _coerce_int_list(raw: Any) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out: list[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


def _parse_monthday_range(raw: Any) -> tuple[int, int] | None:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return int(raw[0]), int(raw[1])
        except (TypeError, ValueError):
            return None
    if isinstance(raw, str):
        text = raw.strip().lower().replace('to', ' ').replace('-', ' ')
        parts = [p for p in text.split() if p.isdigit()]
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
    return None


def normalize_when(when: Any) -> dict[str, Any]:
    """
    统一 when 结构。支持 v3 原生与示例.json 别名：
    - weekday / every + day_in_week
    - monthday / list
    - monthday_range / to
    - range（ISO 日期闭区间）
    """
    if not isinstance(when, dict):
        return {}
    w = dict(when)
    out: dict[str, Any] = {}

    # weekday
    if 'weekday' in w:
        wd = w['weekday']
        if isinstance(wd, str) and wd.lower() in ('all', 'every', 'daily', '*'):
            out['weekday'] = list(_WEEKDAY_ALL)
        else:
            out['weekday'] = _coerce_int_list(wd)
    elif str(w.get('day_type') or '').lower() == 'every':
        days = _coerce_int_list(w.get('day_in_week'))
        out['weekday'] = list(_WEEKDAY_ALL) if set(days) >= set(_WEEKDAY_ALL) else days

    # monthday
    if 'monthday' in w:
        out['monthday'] = _coerce_int_list(w['monthday'])
    elif str(w.get('day_type') or '').lower() == 'list':
        out['monthday'] = _coerce_int_list(w.get('days') or w.get('day_list') or w.get('list'))

    # monthday_range（自然月内连续日号）
    mdr = w.get('monthday_range')
    if mdr is None and str(w.get('day_type') or '').lower() == 'to':
        mdr = w.get('to') or w.get('range_days')
    parsed_mdr = _parse_monthday_range(mdr)
    if parsed_mdr:
        out['monthday_range'] = list(parsed_mdr)

    # ISO range
    iso_range = w.get('range')
    if iso_range is None and isinstance(w.get('from'), str):
        iso_range = [w.get('from'), w.get('to')]
    if isinstance(iso_range, (list, tuple)) and len(iso_range) >= 2:
        out['range'] = [str(iso_range[0]).strip(), str(iso_range[1]).strip()]

    return out


def when_matches(when: Any, on_date: date) -> bool:
    w = normalize_when(when)
    if not w:
        return False

    checks: list[bool] = []
    if 'weekday' in w:
        days = w['weekday'] or list(_WEEKDAY_ALL)
        checks.append(on_date.isoweekday() in days)
    if 'monthday' in w:
        checks.append(on_date.day in w['monthday'])
    if 'monthday_range' in w:
        start, end = int(w['monthday_range'][0]), int(w['monthday_range'][1])
        if start <= end:
            checks.append(start <= on_date.day <= end)
        else:
            checks.append(on_date.day >= start or on_date.day <= end)
    if 'range' in w:
        start = _parse_iso_date(w['range'][0])
        end = _parse_iso_date(w['range'][1])
        checks.append(bool(start and end and start <= on_date <= end))
    return all(checks) if checks else False


def _merge_quadrant_block(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not patch:
        return dict(base)
    out = dict(base)
    for key, value in patch.items():
        if key in ('tag', 'source', 'priority'):
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            nested = dict(out[key])
            nested.update(value)
            out[key] = nested
        else:
            out[key] = value
    return out


def _merge_day_quadrants(
    base: dict[str, dict[str, Any]],
    patch: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    out = {k: dict(v) for k, v in base.items()}
    for quadrant, block in (patch or {}).items():
        q = str(quadrant)
        if q not in QUADRANT_KEYS or not isinstance(block, dict):
            continue
        out[q] = _merge_quadrant_block(out.get(q) or {}, block)
    return out


def tag_to_quadrants(tag_body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(tag_body, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for q in QUADRANT_KEYS:
        block = tag_body.get(q)
        if isinstance(block, dict) and block:
            out[q] = dict(block)
    return out


def resolve_global_day_from_calendar(calendar: dict[str, Any], date_str: str) -> dict[str, dict[str, Any]]:
    """
    从完整日历 dict 解析某日四色象限。
    顺序：v3 schedules（低→高 priority 叠加）→ v2 days[date] 覆盖。
    """
    on_date = _parse_iso_date(date_str)
    if on_date is None:
        return {}

    version = int(calendar.get('version') or 2)
    merged: dict[str, dict[str, Any]] = {}

    if version >= 3:
        tags = calendar.get('tags') or {}
        schedules = calendar.get('schedules') or []
        if not isinstance(tags, dict):
            tags = {}
        if not isinstance(schedules, list):
            schedules = []

        entries: list[tuple[int, str, dict[str, Any]]] = []
        for row in schedules:
            if not isinstance(row, dict):
                continue
            tag_name = str(row.get('tag') or '').strip()
            if not tag_name or tag_name not in tags:
                continue
            if not when_matches(row.get('when'), on_date):
                continue
            try:
                priority = int(row.get('priority', 0))
            except (TypeError, ValueError):
                priority = 0
            tag_body = tags.get(tag_name)
            if not isinstance(tag_body, dict):
                continue
            entries.append((priority, tag_name, tag_body))

        entries.sort(key=lambda x: (x[0], x[1]))
        for priority, tag_name, tag_body in entries:
            quads = tag_to_quadrants(tag_body)
            stamped: dict[str, dict[str, Any]] = {}
            for q, block in quads.items():
                b = dict(block)
                b['_tag'] = tag_name
                b['_priority'] = priority
                stamped[q] = b
            merged = _merge_day_quadrants(merged, stamped)

    # v2 逐日（显式条目覆盖规则结果）
    days = calendar.get('days') or {}
    if isinstance(days, dict):
        legacy = days.get(str(date_str))
        if isinstance(legacy, dict):
            legacy_quads = {
                q: dict(legacy[q])
                for q in QUADRANT_KEYS
                if isinstance(legacy.get(q), dict)
            }
            merged = _merge_day_quadrants(merged, legacy_quads)

    return merged


def resolve_matched_tags(calendar: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    """调试/溯源：返回某日命中的 schedule 列表（按 priority 升序）。"""
    on_date = _parse_iso_date(date_str)
    if on_date is None or int(calendar.get('version') or 2) < 3:
        return []
    tags = calendar.get('tags') or {}
    schedules = calendar.get('schedules') or []
    out: list[dict[str, Any]] = []
    for row in schedules:
        if not isinstance(row, dict):
            continue
        tag_name = str(row.get('tag') or '').strip()
        if not tag_name or tag_name not in tags:
            continue
        if not when_matches(row.get('when'), on_date):
            continue
        try:
            priority = int(row.get('priority', 0))
        except (TypeError, ValueError):
            priority = 0
        out.append({
            'tag': tag_name,
            'priority': priority,
            'when': normalize_when(row.get('when')),
        })
    out.sort(key=lambda x: (x['priority'], x['tag']))
    return out
