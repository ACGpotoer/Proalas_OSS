# -*- coding: utf-8 -*-
"""自动突破：艘数 / 间隔 / 船坞稀有度筛选。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from module.proalas.dock_filter_map import get_section, list_keys

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

RARITY_OPTIONS = [k for k in list_keys('rarity') if k != 'ultra']

RARITY_LABEL_ZH: dict[str, str] = {
    str(o['key']): str(o.get('label_zh') or o['key'])
    for o in get_section('rarity').get('options') or []
    if str(o['key']) != 'ultra'
}

FACTION_BREAK_KEYS = [k for k in list_keys('faction') if k not in ('all', 'meta')]

# 稀有度选「全部」时：点除海上传奇外全部稀有度项
RARITY_ALL_APPLY_KEYS = [k for k in list_keys('rarity') if k != 'ultra']


def parse_ships_per_run(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoBreak_ShipsPerRun', 2)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 2
    return max(1, min(7, n))


def parse_run_interval_days(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoBreak_RunIntervalDays', 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(7, n))


def parse_ship_rarity(config: 'AzurLaneConfig') -> str:
    raw = getattr(config, 'ProalasAutoBreak_ShipRarity', None)
    if raw is None:
        legacy = str(getattr(config, 'ProalasAutoBreak_StarQuality', 'SSR') or 'SSR').strip().upper()
        legacy_map = {'SSR': 'super_rare', 'SR': 'elite'}
        raw = legacy_map.get(legacy, 'all')
    key = str(raw if raw is not None else 'all').strip()
    if key not in RARITY_OPTIONS:
        return 'all'
    return key


def rarity_label_zh(key: str) -> str:
    return RARITY_LABEL_ZH.get(key, key)
