# -*- coding: utf-8 -*-
"""UP 船坞检索坐标与模板 — ProAlas autoGacha 船坞搜索流程。"""
from __future__ import annotations

from typing import List, Tuple

from module.base.button import Button

Area4 = Tuple[int, int, int, int]
Click = Tuple[int, int]

_AFTER_CLICK = 2.5
_STEP_PAUSE = 1.0
_AFTER_UI = 1.0
_AFTER_INPUT_FOCUS = 1.0
_AFTER_INPUT_PASTE = 1.0
_AFTER_DISMISS_TAP = 1.0
_AFTER_RESULT = 1.0
_BETWEEN_SHIPS = 1.5
_AFTER_SEARCH = 2.0
_AFTER_MATCH = 1.0
_TEMPLATE_SIMILARITY = 0.85
_MAX_NAV_RETRY = 3
_CLIPBOARD_RETRY = 3

# ---------- 点击坐标 ----------
CLICK_MAIN_TO_DOCK: Click = (250, 680)
CLICK_SEARCH_ICON: Click = (665, 28)
CLICK_SEARCH_INPUT: Click = (800, 35)
CLICK_DISMISS_DROPDOWN: Click = (160, 30)
DISMISS_DROPDOWN_TIMES = 2
RETURN_MAIN_CLICK: Click = (1230, 30)

# 兼容旧引用
DOCK_NAV_CLICKS: List[Click] = [CLICK_MAIN_TO_DOCK, CLICK_SEARCH_ICON, CLICK_SEARCH_INPUT]
DOCK_SEARCH_INPUT_OCR: Area4 = (120, 8, 960, 120)
DOCK_SEARCH_CONFIRM_CLICK: Click = (600, 400)

# ---------- 船坞页锚点（进入船坞后右上区域） ----------
BOAT_AWAY_USE_AREA: Area4 = (700, 5, 980, 50)

BOAT_AWAY_USE = Button(
    area={'cn': BOAT_AWAY_USE_AREA},
    color={'cn': (128, 92, 78)},
    button={'cn': BOAT_AWAY_USE_AREA},
    file={'cn': './assets/cn/GachaUp/BoatAwayUse.png'},
    name='BoatAwayUse',
)

# ---------- 搜索框已展开 ----------
SEARCH_YES_AREA: Area4 = (650, 5, 695, 50)

SEARCH_YES = Button(
    area={'cn': SEARCH_YES_AREA},
    color={'cn': (77, 126, 161)},
    button={'cn': SEARCH_YES_AREA},
    file={'cn': './assets/cn/GachaUp/SearchYes.png'},
    name='SearchYes',
)

SEARCH_YES_FILE = './assets/cn/GachaUp/SearchYes.png'

# ---------- 检索结果：未拥有（空结果块，ProAlas SearchBoatNull 黑底 1280×720） ----------
SEARCH_BOAT_NULL: Area4 = (0, 100, 1280, 600)
SEARCH_BOAT_NULL_FILE = './assets/cn/GachaUp/SEARCH_BOAT_NULL.png'
SEARCH_BOAT_NULL_THRESHOLD = 0.95

SEARCH_BOAT_NULL_BTN = Button(
    area={'cn': SEARCH_BOAT_NULL},
    color={'cn': (128, 128, 128)},
    button={'cn': SEARCH_BOAT_NULL},
    file={'cn': SEARCH_BOAT_NULL_FILE},
    name='SearchBoatNull',
)

# ADB KEYCODE_PASTE
KEYCODE_PASTE = 279
