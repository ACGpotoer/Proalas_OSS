# -*- coding: utf-8 -*-
"""船坞筛选映射表加载（dock_filter_map.yaml）。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MAP_PATH = Path(__file__).with_name('dock_filter_map.yaml')
_SECTIONS = ('index', 'faction', 'rarity', 'extra')


@lru_cache(maxsize=1)
def load_map() -> dict[str, Any]:
    with _MAP_PATH.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_section(name: str) -> dict[str, Any]:
    data = load_map()
    if name not in _SECTIONS:
        raise KeyError(f'unknown dock filter section: {name!r}')
    return data[name]


def get_slot(section: str, key: str) -> dict[str, Any]:
    for opt in get_section(section).get('options') or []:
        if opt.get('key') == key:
            return opt
    raise KeyError(f'{section}.{key} not in dock_filter_map.yaml')


def list_keys(section: str) -> list[str]:
    return [str(o['key']) for o in get_section(section).get('options') or []]
