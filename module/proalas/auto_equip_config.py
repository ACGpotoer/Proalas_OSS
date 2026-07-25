# -*- coding: utf-8 -*-
"""自动换装备和配置装备：用户可选项解析。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

_EQUIP_QUALITY = frozenset({'blue', 'purple', 'gold'})
_COIN_LIMITS = (100000, 150000, 200000, 300000, 500000)
_WAREHOUSE_RESERVE = (5, 10, 15, 20, 30)


def parse_equip_quality(config: 'AzurLaneConfig') -> str:
    raw = str(getattr(config, 'ProalasAutoEquip_EquipQuality', 'purple') or 'purple').strip().lower()
    return raw if raw in _EQUIP_QUALITY else 'purple'


def parse_replace_surplus_purple(config: 'AzurLaneConfig') -> bool:
    return _as_bool(getattr(config, 'ProalasAutoEquip_ReplaceSurplusPurple', True))


def parse_allow_craft(config: 'AzurLaneConfig') -> bool:
    return _as_bool(getattr(config, 'ProalasAutoEquip_AllowCraft', False))


def parse_craft_coin_limit(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoEquip_CraftCoinLimit', 300000)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 300000
    if n in _COIN_LIMITS:
        return n
    return min(_COIN_LIMITS, key=lambda x: abs(x - n))


def parse_warehouse_reserve(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoEquip_WarehouseReserve', 10)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 10
    if n in _WAREHOUSE_RESERVE:
        return n
    return max(5, min(30, n))


def parse_team_no(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoEquip_TeamNo', 3)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3
    return max(1, min(6, n))


def _as_bool(raw) -> bool:
    if isinstance(raw, str):
        return raw.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(raw)
