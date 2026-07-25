# -*- coding: utf-8 -*-
"""AI 规划策略切换：日限额 + StrategyChangedAt 持久化。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.proalas.ai_planner.strategies import normalize_strategy
from module.proalas.feature_gate import get_effective_plan

STRATEGY_CHANGES_PER_DAY_AUTO = 1


def _parse_dt(text: Any) -> datetime | None:
    if text is None or text == '':
        return None
    if hasattr(text, 'strftime'):
        return text.replace(microsecond=0) if hasattr(text, 'replace') else text
    raw = str(text).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw[:19], fmt).replace(microsecond=0)
        except ValueError:
            continue
    return None


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def effective_auto_apply(config) -> bool:
    """Pro+ / 创新·人工 默认不自动 apply。"""
    if not bool(getattr(config, 'ProalasAiPlanner_AutoApply', True)):
        return False
    if get_effective_plan(config) == 'pro_plus':
        return False
    strategy = normalize_strategy(getattr(config, 'ProalasAiPlanner_Strategy', ''))
    if strategy == 'innovative':
        return False
    return True


def read_strategy_meta(device_id: str) -> dict[str, Any]:
    data = read_file(filepath_config(device_id))
    if not isinstance(data, dict):
        return {}
    meta = deep_get(data, ['ProalasData', 'AiPlannerMeta'], None)
    return dict(meta) if isinstance(meta, dict) else {}


def _write_strategy_meta(device_id: str, meta: dict[str, Any]) -> None:
    path = filepath_config(device_id)
    data = read_file(path)
    if not isinstance(data, dict):
        return
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    proalas['AiPlannerMeta'] = meta
    deep_set(data, keys=['ProalasData'], value=proalas)
    write_file(path, data)


def check_strategy_change_allowed(
    config,
    device_id: str,
    new_strategy: str,
) -> tuple[bool, str]:
    sid = normalize_strategy(new_strategy)
    current = normalize_strategy(getattr(config, 'ProalasAiPlanner_Strategy', ''))
    if sid == current:
        return False, '已是当前策略'

    if not effective_auto_apply(config):
        return True, ''

    meta = read_strategy_meta(device_id)
    changed_at = _parse_dt(meta.get('strategyChangedAt'))
    if changed_at is None:
        return True, ''

    if changed_at.strftime('%Y-%m-%d') != _today_str():
        return True, ''

    count = int(meta.get('strategyChangesToday') or 0)
    if count >= STRATEGY_CHANGES_PER_DAY_AUTO:
        return False, '自动规划模式下，策略每日仅可切换 1 次（下次规划周期生效）'
    return True, ''


def record_strategy_change(device_id: str, strategy_id: str) -> None:
    sid = normalize_strategy(strategy_id)
    now = datetime.now().replace(microsecond=0)
    meta = read_strategy_meta(device_id)
    prev_at = _parse_dt(meta.get('strategyChangedAt'))
    if prev_at and prev_at.strftime('%Y-%m-%d') == _today_str():
        count = int(meta.get('strategyChangesToday') or 0) + 1
    else:
        count = 1
    meta.update({
        'strategyChangedAt': now.strftime('%Y-%m-%d %H:%M:%S'),
        'strategyChangesToday': count,
        'lastStrategy': sid,
    })
    _write_strategy_meta(device_id, meta)


def strategy_switch_hint(config) -> str:
    if not effective_auto_apply(config):
        return 'Pro+ / 手动模式：策略切换不限次'
    return f'自动模式：策略每日最多切换 {STRATEGY_CHANGES_PER_DAY_AUTO} 次'
