# -*- coding: utf-8 -*-
"""AI 指令本地门禁：stale / 资源门槛 / 日变更去重。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.deep import deep_get
from module.config.utils import filepath_config, read_file
from module.proalas.ai_planner.history_store import list_history
from module.proalas.ai_planner.strategies import STRATEGY_AGGRESSIVE, normalize_strategy

MAX_SET_CHANGES_PER_PATH_PER_DAY = 1
MAX_TASK_DELAY_PER_TASK_PER_DAY = 2

AGGRESSIVE_MIN_OIL = 8000
AGGRESSIVE_MIN_MONEY = 100000


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _coerce_number(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _paths_changed_today(device_id: str) -> set[str]:
    paths: set[str] = set()
    data = read_file(filepath_config(device_id))
    if not isinstance(data, dict):
        return paths

    red_plan = deep_get(data, ['ProalasData', 'RedPlan'], {}) or {}
    if isinstance(red_plan, dict) and str(red_plan.get('date') or '') == _today_str():
        for detail in red_plan.get('details') or []:
            text = str(detail)
            if text.startswith('set '):
                path_part = text[4:].split('→', 1)[0].split('=', 1)[0].strip()
                if path_part:
                    paths.add(path_part)

    for row in list_history(device_id, limit=20):
        if not row.get('applied'):
            continue
        at = str(row.get('at') or '')[:10]
        if at != _today_str():
            continue
        for cmd in row.get('commands') or []:
            if isinstance(cmd, dict) and str(cmd.get('op') or '').lower() == 'set':
                path = str(cmd.get('path') or '').strip()
                if path:
                    paths.add(path)
    return paths


def _task_delay_counts_today(device_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in list_history(device_id, limit=20):
        if not row.get('applied'):
            continue
        at = str(row.get('at') or '')[:10]
        if at != _today_str():
            continue
        for cmd in row.get('commands') or []:
            if not isinstance(cmd, dict):
                continue
            if str(cmd.get('op') or '').lower() != 'task_delay':
                continue
            task = str(cmd.get('task') or '').strip()
            if task:
                counts[task] = counts.get(task, 0) + 1
    return counts


def post_process_commands(
    commands: list[dict[str, Any]],
    context: dict[str, Any],
    device_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    过滤 LLM 指令。返回 (保留指令, warnings)。
    stale 或激进资源不足时返回空列表。
    """
    warnings: list[str] = []
    if not commands:
        return [], warnings

    resources = context.get('resources') or {}
    if resources.get('stale'):
        warnings.append('资源数据过期（Collector stale），已跳过全部 apply')
        return [], warnings

    strategy = normalize_strategy(context.get('strategyId'))
    if strategy == STRATEGY_AGGRESSIVE:
        oil = _coerce_number(resources.get('oil'))
        money = _coerce_number(resources.get('money'))
        oil_ok = oil is not None and oil >= AGGRESSIVE_MIN_OIL
        money_ok = money is not None and money >= AGGRESSIVE_MIN_MONEY
        if not oil_ok and not money_ok:
            warnings.append(
                f'激进策略需 oil>={AGGRESSIVE_MIN_OIL} 或 money>={AGGRESSIVE_MIN_MONEY}，'
                '已跳过全部 apply'
            )
            return [], warnings

    paths_today = _paths_changed_today(device_id)
    delay_counts = _task_delay_counts_today(device_id)
    kept: list[dict[str, Any]] = []

    for cmd in commands:
        op = str(cmd.get('op') or '').lower()
        if op == 'set':
            path = str(cmd.get('path') or '').strip()
            if path in paths_today:
                warnings.append(f'今日已改过 {path}，跳过重复 set')
                continue
        elif op == 'task_delay':
            task = str(cmd.get('task') or '').strip()
            if delay_counts.get(task, 0) >= MAX_TASK_DELAY_PER_TASK_PER_DAY:
                warnings.append(f'今日 {task} task_delay 已达上限，跳过')
                continue
            delay_counts[task] = delay_counts.get(task, 0) + 1
        kept.append(cmd)

    return kept, warnings
