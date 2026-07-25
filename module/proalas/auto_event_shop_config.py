# -*- coding: utf-8 -*-
"""活动商店兑换：配置解析。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

DEFAULT_PRIORITY = '2UR>UR>SSR_BOX>SSR_CAT>SSR_BOAT>XIN2>XIN1>SR_CAT>OTHER'
UR_FIRST_PRIORITY = DEFAULT_PRIORITY


def parse_shop_count(config: 'AzurLaneConfig') -> int:
    raw = getattr(config, 'ProalasAutoEventShop_ShopCount', 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(3, n))


def parse_priority_mode(config: 'AzurLaneConfig') -> str:
    raw = getattr(config, 'ProalasAutoEventShop_PriorityMode', 'ur_first')
    return str(raw or 'ur_first').strip().lower()


def parse_priority_string(config: 'AzurLaneConfig') -> str:
    mode = parse_priority_mode(config)
    if mode == 'custom':
        raw = getattr(config, 'ProalasAutoEventShop_CustomPriority', DEFAULT_PRIORITY)
        text = str(raw or '').strip()
        return text if text else DEFAULT_PRIORITY
    return UR_FIRST_PRIORITY


def format_token_ur_item(value: int | None) -> str:
    if value is None:
        return '—'
    return f'URITEM-{int(value)}'


def format_token_pt(value: int | None) -> str:
    if value is None:
        return '—'
    return f'PT-{int(value)}'
