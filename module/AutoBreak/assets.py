# -*- coding: utf-8 -*-
"""
自动突破坐标与模板（船坞筛选 + TupoInto/Yes Tab）。

突破 Tab 双搜索区（各 50×50）：
  slot1 (20,220)-(70,270)
  slot2 (20,315)-(70,365)
TupoInto / TupoIntoYes 均在两区分别比对，命中哪区点/验哪区中心。
"""
from __future__ import annotations

from typing import Dict, Tuple

from module.base.button import Button
from module.FleetStrength import assets as FA

Click = Tuple[int, int]
Area4 = Tuple[int, int, int, int]

# ---------- 船坞 ----------
CLICK_MAIN_TO_DOCK: Click = (250, 680)
CLICK_SELECT_SHIP: Click = (320, 210)
CLICK_BACK_DETAIL: Click = FA.CLICK_RETURN_DETAIL  # (50, 50)
CLICK_RETURN_MAIN: Click = (1230, 30)

# ---------- 突破 Tab 双搜索区 ----------
TUPO_TAB_SEARCH_AREAS: Dict[int, Area4] = {
    1: (20, 220, 70, 270),
    2: (20, 315, 70, 365),
}

TUPO_INTO_REF_AREA: Area4 = (20, 220, 70, 270)
TUPO_INTO_FILE = './assets/cn/AutoBreak/TupoInto.png'

TUPO_INTO_YES_REF_AREA: Area4 = (20, 220, 70, 270)
TUPO_INTO_YES_FILE = './assets/cn/AutoBreak/TupoIntoYes.png'

TUPO_INTO = Button(
    area={'cn': TUPO_TAB_SEARCH_AREAS[1]},
    color={'cn': (112, 95, 70)},
    button={'cn': TUPO_TAB_SEARCH_AREAS[1]},
    file={'cn': TUPO_INTO_FILE},
    name='TupoInto',
)

TUPO_INTO_YES = Button(
    area={'cn': TUPO_TAB_SEARCH_AREAS[1]},
    color={'cn': (92, 121, 157)},
    button={'cn': TUPO_TAB_SEARCH_AREAS[1]},
    file={'cn': TUPO_INTO_YES_FILE},
    name='TupoIntoYes',
)

_TUPO_INTO_SIMILARITY = 0.88
_TUPO_INTO_YES_SIMILARITY = 0.86
_MAX_TUPO_TAB_ATTEMPTS = 3

# ---------- 突破确认（旧版 TUPODO 前三击）----------
CLICKS_TUPO_DO: tuple[Click, ...] = (
    (888, 665),
    (821, 520),
    (1174, 663),
)

MIN_CLICK_INTERVAL = 1.0
_AFTER_CLICK = 1.2
_SAME_POS_EXTRA_DELAY = 1.5
_AFTER_FILTER = 0.45
_AFTER_DOCK = 0.6
_AFTER_MATCH = 0.8
_AFTER_TUPO_TAB = 0.5
_TEMPLATE_SIMILARITY = 0.85


def area_center(area: Area4) -> Click:
    x1, y1, x2, y2 = area
    return (x1 + x2) // 2, (y1 + y2) // 2
