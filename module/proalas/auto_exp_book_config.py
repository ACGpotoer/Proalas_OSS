# -*- coding: utf-8 -*-
"""自动使用经验书：品质 / 每轮喂食次数 / 调度间隔。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from module.proalas.dock_filter_map import get_section, list_keys

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

RARITY_OPTIONS = list_keys('rarity')

RARITY_LABEL_ZH: dict[str, str] = {
    str(o['key']): str(o.get('label_zh') or o['key'])
    for o in get_section('rarity').get('options') or []
}


def parse_ship_rarity(config: 'AzurLaneConfig') -> str:
    raw = getattr(config, 'ProalasAutoExpBook_ShipRarity', 'all')
    key = str(raw if raw is not None else 'all').strip()
    if key not in RARITY_OPTIONS:
        return 'all'
    return key


def parse_feed_rounds(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoExpBook_FeedRoundsPerRun', 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(5, n))


def parse_run_interval_days(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoExpBook_RunIntervalDays', 7)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 7
    return max(1, min(7, n))


def rarity_label_zh(key: str) -> str:
    return RARITY_LABEL_ZH.get(key, key)
