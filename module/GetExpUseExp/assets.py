# -*- coding: utf-8 -*-
"""
自动获取/使用经验书坐标（来自 ProAlas IO_Core/event/autoGetEXP、autoUseEXP/assets.py）。
"""
from __future__ import annotations

from typing import List, Tuple

Click = Tuple[int, int]
Area4 = Tuple[int, int, int, int]

# ---------- autoGetEXP ----------
CLICKS_PREFIX: List[Click] = [
    (426, 684),
    (1262, 566),
    (1262, 566),
]

LAST_THREE_CLICKS: List[Click] = [
    (1262, 566),
    (1262, 566),
    (1262, 514),
]

# 演习列表 OCR 区域（多行扫描）
YANXI_LIST_AREA: Area4 = (80, 120, 1200, 680)
YANXI_LIST_ROW_COUNT = 12

TARGET_TEXT = '演习'

EXP_AREA: Area4 = (440, 400, 500, 430)
EXP_OCR_SCALE = 8.0

RETURN_TO_MAIN_CLICKS: List[Click] = [
    (635, 510),
    (1230, 30),
]

RETURN_FROM_LIST_CLICKS: List[Click] = [
    (1230, 30),
]

# ---------- autoUseEXP ----------
USE_EXP_CLICKS: List[Click] = [
    (260, 684),
    (1151, 32),
    (284, 500),
    (290, 422),
    (290, 293),
    (290, 164),
    (1031, 490),
    (805, 646),
    (334, 177),
    (850, 289),
    (667, 550),
    (887, 551),
    (857, 491),
    (857, 491),
    (642, 610),
    (1232, 34),
]

MIN_CLICK_INTERVAL = 1.0
_AFTER_CLICK = 1.2
_SAME_POS_EXTRA_DELAY = 1.5
_AFTER_NAV = 0.8
_FIND_TEXT_MAX_ATTEMPTS = 3
_FIND_TEXT_INTERVAL = 0.8
