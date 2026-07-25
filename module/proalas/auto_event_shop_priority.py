# -*- coding: utf-8 -*-
"""活动商店兑换优先级链解析（> 分隔）。"""
from __future__ import annotations

import re

_VALID_TAGS = frozenset({
    '2UR', 'UR', 'SSR_BOX', 'SSR_CAT', 'SSR_BOAT',
    'XIN2', 'XIN1', 'SR_CAT', 'OTHER',
})


def parse_priority_chain(text: str) -> list[str]:
    """将 `2UR>UR>SSR_BOX>...` 解析为有序标签列表（去空白、去重保留首次）。"""
    if not text:
        return []
    parts = re.split(r'\s*>\s*', str(text).strip())
    chain: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = part.strip().upper()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        chain.append(tag)
    return chain


def validate_priority_chain(chain: list[str]) -> list[str]:
    unknown = [t for t in chain if t not in _VALID_TAGS]
    if unknown:
        from module.logger import logger
        logger.warning('EventShop 未知优先级标签: %s', unknown)
    return [t for t in chain if t in _VALID_TAGS]
