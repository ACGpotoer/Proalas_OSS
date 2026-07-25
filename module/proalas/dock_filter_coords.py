# -*- coding: utf-8 -*-
"""船坞筛选面板坐标生成（与 module/retire/dock.py ButtonGrid 对齐，1280×720 cn）。"""
from __future__ import annotations

from typing import Any

DELTA = (147 + 1 / 3, 57)
BUTTON_SHAPE = (139, 42)


def _area(col: int, row: int, origin: tuple[int, int]) -> tuple[int, int, int, int]:
    x = int(round(origin[0] + col * DELTA[0]))
    y = int(round(origin[1] + row * DELTA[1]))
    return x, y, x + BUTTON_SHAPE[0], y + BUTTON_SHAPE[1]


def _click(area: tuple[int, int, int, int]) -> list[int]:
    return [(area[0] + area[2]) // 2, (area[1] + area[3]) // 2]


def _slot(key: str, label_zh: str, col: int, row: int, origin: tuple[int, int]) -> dict[str, Any]:
    crop = _area(col, row, origin)
    return {
        'key': key,
        'label_zh': label_zh,
        'row': row,
        'col': col,
        'click': _click(crop),
        'crop': list(crop),
    }


def _section(
    name: str,
    label: str,
    origin: tuple[int, int],
    grid_shape: tuple[int, int],
    default: str,
    options: list[tuple[str, str, int, int]],
) -> dict[str, Any]:
    return {
        'section': name,
        'label': label,
        'origin': list(origin),
        'grid_shape': list(grid_shape),
        'default': default,
        'options': [_slot(key, zh, col, row, origin) for key, zh, col, row in options],
    }


# cn @Config.when(SERVER=None) — 2026 船坞 UI 更新后
ORIGIN_SORT = (218, 36)
ORIGIN_INDEX = (218, 109)
ORIGIN_FACTION = (218, 239)
ORIGIN_RARITY = (218, 427)
ORIGIN_EXTRA = (218, 499)

INDEX_OPTIONS = [
    ('all', '全部', 0, 0),
    ('vanguard', '前排先锋', 1, 0),
    ('main', '后排主力', 2, 0),
    ('dd', '驱逐', 3, 0),
    ('cl', '轻巡', 4, 0),
    ('ca', '重巡', 5, 0),
    ('bb', '战列', 6, 0),
    ('cv', '航母', 0, 1),
    ('repair', '维修', 1, 1),
    ('ss', '潜艇', 2, 1),
    ('others', '其他', 3, 1),
]

FACTION_OPTIONS = [
    ('all', '全阵营', 0, 0),
    ('eagle', '白鹰', 1, 0),
    ('royal', '皇家', 2, 0),
    ('sakura', '重樱', 3, 0),
    ('iron', '铁血', 4, 0),
    ('dragon', '东煌', 5, 0),
    ('sardegna', '撒丁帝国', 6, 0),
    ('northern', '北方联合', 0, 1),
    ('iris', '自由鸢尾', 1, 1),
    ('vichya', '维希教廷', 2, 1),
    ('tulipa', '郁金王国', 3, 1),
    ('pedreria', '晶环联盟', 4, 1),
    ('meta', 'META', 5, 1),
    ('tempesta', '飓风', 6, 1),
    ('other', '其他', 0, 2),
]

RARITY_OPTIONS = [
    ('all', '全部', 0, 0),
    ('common', '普通', 1, 0),
    ('rare', '稀有', 2, 0),
    ('elite', '精锐', 3, 0),
    ('super_rare', '超稀有', 4, 0),
    ('ultra', '海上传奇', 5, 0),
]

EXTRA_OPTIONS = [
    ('no_limit', '无限制', 0, 0),
    ('has_skin', '可换装', 1, 0),
    ('can_retrofit', '可改造', 2, 0),
    ('enhanceable', '可强化', 3, 0),
    ('can_limit_break', '可突破', 4, 0),
    ('not_level_max', '未满级', 5, 0),
    ('can_awaken', '可以认知觉醒', 6, 0),
    ('can_awaken_plus', '可以认知觉醒II', 0, 1),
    ('special', '特殊', 1, 1),
    ('oath_skin', '誓约换装', 2, 1),
    ('unique_augment_module', '专属兵装', 3, 1),
    ('wear_skin', '已换装', 4, 1),
    ('oathed', '已誓约', 5, 1),
]

FACTION_KEYS = [k for k, *_ in FACTION_OPTIONS]


def build_map_dict() -> dict[str, Any]:
    return {
        'version': 2,
        'gameSize': [1280, 720],
        'grid': {
            'delta': list(DELTA),
            'button_shape': list(BUTTON_SHAPE),
        },
        'index': _section('index', '索引', ORIGIN_INDEX, (7, 2), 'all', INDEX_OPTIONS),
        'faction': _section('faction', '阵营', ORIGIN_FACTION, (7, 3), 'all', FACTION_OPTIONS),
        'rarity': _section('rarity', '稀有度', ORIGIN_RARITY, (7, 1), 'all', RARITY_OPTIONS),
        'extra': _section('extra', '附加索引', ORIGIN_EXTRA, (7, 2), 'no_limit', EXTRA_OPTIONS),
    }
