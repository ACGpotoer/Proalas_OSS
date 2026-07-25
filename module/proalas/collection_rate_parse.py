# -*- coding: utf-8 -*-
"""收藏率 HUD 解析（与 ProAlas getBoatMessage 规则一致）。"""
from __future__ import annotations


def parse_collection_rate_percent(digits: str, boat_max: int) -> tuple[float, bool]:
    """
    收藏率 HUD 数字解析：
    - 802 → 80.2%
    - 100 且 boat_max>700 → 100%，否则 → 10.0%
    """
    digits = (digits or '').strip()
    if not digits:
        return 0.0, False

    if len(digits) > 3:
        digits = digits[:3]

    if len(digits) >= 3 and set(digits) == {'9'}:
        return 0.0, False

    if len(digits) == 3:
        if digits == '100':
            if boat_max > 700:
                return 100.0, True
            return 10.0, True
        try:
            percent = float(f'{digits[:2]}.{digits[2]}')
        except ValueError:
            return 0.0, False
        return percent, 0.0 < percent <= 100.0

    if len(digits) in (1, 2):
        try:
            percent = float(digits)
        except ValueError:
            return 0.0, False
        return percent, 0.0 < percent <= 100.0

    return 0.0, False
