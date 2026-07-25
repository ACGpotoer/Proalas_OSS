# -*- coding: utf-8 -*-
"""自动补齐图鉴：总开关 / 子开关 / 科研周更到期判定。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from module.config.deep import deep_get
from module.config.utils import get_server_last_update

_PATH = ['ProalasCollectionFill', 'ProalasCollectionFill']
DEFAULT_RESEARCH_INTERVAL_DAYS = 7


def _bool(config_data: dict[str, Any], key: str, default: bool = False) -> bool:
    return bool(deep_get(config_data, _PATH + [key], default))


def collection_fill_enabled(config_data: dict[str, Any]) -> bool:
    """总开关；缺省 True，兼容旧配置。"""
    raw = deep_get(config_data, _PATH + ['Enable'], None)
    if raw is None:
        return True
    return bool(raw)


def build_fill_enabled(config_data: dict[str, Any]) -> bool:
    if not collection_fill_enabled(config_data):
        return False
    raw = deep_get(config_data, _PATH + ['BuildEnable'], None)
    if raw is None:
        return True
    return bool(raw)


def farm_fill_enabled(config_data: dict[str, Any]) -> bool:
    if not collection_fill_enabled(config_data):
        return False
    return _bool(config_data, 'FarmEnable', False)


def research_fill_enabled(config_data: dict[str, Any]) -> bool:
    if not collection_fill_enabled(config_data):
        return False
    raw = deep_get(config_data, _PATH + ['ResearchEnable'], None)
    if raw is None:
        return True
    return bool(raw)


def research_interval_days(config_data: dict[str, Any]) -> int:
    """间隔天数；0 = 立刻（每次定时计划都到期，测试用）。"""
    raw = deep_get(
        config_data,
        _PATH + ['ResearchIntervalDays'],
        DEFAULT_RESEARCH_INTERVAL_DAYS,
    )
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RESEARCH_INTERVAL_DAYS
    return max(0, min(30, n))


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


def research_last_scan_at(config_data: dict[str, Any]) -> datetime | None:
    research = deep_get(config_data, ['ProalasData', 'CollectionFill', 'research'], {}) or {}
    if not isinstance(research, dict):
        return None
    return _parse_iso(
        research.get('lastScanAt')
        or research.get('updatedAt')
        or research.get('lastCheckAt')
    )


def research_next_scan_at(config_data: dict[str, Any]) -> datetime | None:
    """全图鉴科研完成后的硬推迟（如 +180 天）；优先于常规间隔。"""
    research = deep_get(config_data, ['ProalasData', 'CollectionFill', 'research'], {}) or {}
    if not isinstance(research, dict):
        return None
    return _parse_iso(research.get('nextResearchScanAt'))


def research_scan_due(config_data: dict[str, Any]) -> bool:
    """距上次扫描（服务器日 04:00 对齐）是否已满 ResearchIntervalDays。"""
    if not research_fill_enabled(config_data):
        return False
    now = datetime.now()
    paused_until = research_next_scan_at(config_data)
    if paused_until is not None and now < paused_until:
        return False
    interval = research_interval_days(config_data)
    # 0 = 立刻（测试）：每次定时计划都扫（仍尊重 nextResearchScanAt 硬推迟）
    if interval == 0:
        return True
    last = research_last_scan_at(config_data)
    if last is None:
        return True
    # 用「上次扫描后第 N 个服务器日切」作为到期点
    boundary = get_server_last_update('04:00')
    due_at = last + timedelta(days=interval)
    return boundary >= due_at


def research_next_due_hint(config_data: dict[str, Any]) -> str:
    if not research_fill_enabled(config_data):
        return '已关闭'
    paused_until = research_next_scan_at(config_data)
    if paused_until is not None and datetime.now() < paused_until:
        return f'全齐推迟至 {paused_until.strftime("%Y-%m-%d")}'
    interval = research_interval_days(config_data)
    if interval == 0:
        return '立刻（测试：每次定时计划）'
    last = research_last_scan_at(config_data)
    if last is None:
        return '待首次扫描'
    due_at = last + timedelta(days=interval)
    if research_scan_due(config_data):
        return f'已到期（间隔 {interval} 天）'
    return f'约 {due_at.strftime("%Y-%m-%d")}（间隔 {interval} 天）'
