# -*- coding: utf-8 -*-
"""编队导航模板与几何常量（ProalasFleetStrength 状态机）。"""
from __future__ import annotations

from typing import Tuple

from module.base.button import Button

Area4 = Tuple[int, int, int, int]
Click = Tuple[int, int]

TEMPLATE_SIMILARITY = 0.85
TEMPLATE_OFFSET = (15, 15)

# ── 导航模板 ──
FLEET_SITUATION_IN_AREA: Area4 = (900, 640, 1020, 700)
FLEET_SITUATION_IN_CENTER: Click = (960, 670)

FleetSituationIn = Button(
    area={'cn': FLEET_SITUATION_IN_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': FLEET_SITUATION_IN_AREA},
    file={'cn': './assets/cn/proalas_nav/FleetSituationIn.png'},
    name='FleetSituationIn',
)

BIANDUI_AREA: Area4 = (1140, 650, 1240, 700)

BianDui = Button(
    area={'cn': BIANDUI_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': BIANDUI_AREA},
    file={'cn': './assets/cn/proalas_nav/BianDui.png'},
    name='BianDui',
)

NULL_BOAT_ADD_CROP = './assets/cn/proalas_nav/NullBoatIF_add_crop.png'

# ── 六槽全屏区域与中心（TEAM_DETAIL 空槽扫描 / 非空点击）──
SHIP_SLOT_RECTS: dict[int, Area4] = {
    1: (60, 150, 230, 600),
    2: (240, 150, 410, 600),
    3: (430, 150, 600, 600),
    4: (695, 150, 865, 600),
    5: (875, 150, 1045, 600),
    6: (1055, 150, 1225, 600),
}

SHIP_SLOT_CENTERS: dict[int, Click] = {
    slot: ((x1 + x2) // 2, (y1 + y2) // 2)
    for slot, (x1, y1, x2, y2) in SHIP_SLOT_RECTS.items()
}

# 空槽「点击添加」相对 mid 带映射（§4.4）
MID_KEEP = 0.4
ADD_RECT_IN_MID: Area4 = (23, 120, 148, 180)

MAX_OPEN_SHIP_RETRIES = 3
