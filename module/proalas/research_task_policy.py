# -*- coding: utf-8 -*-
"""科研任务「能交就交」扫描节奏：默认 72h + 例外。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from module.config.deep import deep_get

DEFAULT_SUBMIT_INTERVAL_HOURS = 72
SHORT_AFTER_TECH1_HOURS = 24


def _parse_iso(raw: Any) -> datetime | None:
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for fmt in (
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%d',
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def _research_block(config_data: dict[str, Any]) -> dict[str, Any]:
    research = deep_get(config_data, ['ProalasData', 'CollectionFill', 'research'], {}) or {}
    return research if isinstance(research, dict) else {}


def research_task_submit_due(config_data: dict[str, Any], *, now: datetime | None = None) -> bool:
    """
    True 应跑任务提交扫描。
    - 从未扫过 / forceNextTaskSubmit → True
    - justSubmittedTechTest1 → 间隔缩短为 24h
    - 默认 72h
    """
    now = now or datetime.now()
    research = _research_block(config_data)
    if research.get('forceNextTaskSubmit'):
        return True
    last = _parse_iso(research.get('lastTaskSubmitAt'))
    if last is None:
        return True
    hours = DEFAULT_SUBMIT_INTERVAL_HOURS
    if research.get('techTest1SubmittedAwaitTech2'):
        hours = SHORT_AFTER_TECH1_HOURS
    return now >= last + timedelta(hours=hours)


def mark_task_submit_ran(
    research: dict[str, Any],
    *,
    submitted_tech_test_1: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """更新 research 块内提交扫描时间戳（调用方写盘）。"""
    now = now or datetime.now()
    out = dict(research)
    out['lastTaskSubmitAt'] = now.isoformat(timespec='seconds')
    out['forceNextTaskSubmit'] = False
    if submitted_tech_test_1:
        out['techTest1SubmittedAwaitTech2'] = True
    # 若本轮已处理过测2 或测1 链路结束，清除短间隔旗（由 submit 模块按结果传）
    return out
