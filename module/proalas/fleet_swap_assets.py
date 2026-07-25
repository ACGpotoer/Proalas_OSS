# -*- coding: utf-8 -*-
"""智能换队坐标（1280×720 cn，用户标定）。"""
from __future__ import annotations

from typing import List, Tuple

from module.FleetStrength import assets as FA
from module.retire.assets import DOCK_FILTER_CONFIRM

Click = Tuple[int, int]
Area4 = Tuple[int, int, int, int]

# 换队专用短延迟（比编队采集的 +3s 保守值快；单槽目标 ~8–10s）
_AFTER_TAP = 0.4
_AFTER_NAV = 0.8
_AFTER_FILTER_OPEN = 0.5
_AFTER_FILTER_CLICK = 0.35
_AFTER_FILTER_DONE = 0.45
_AFTER_PICK = 0.45
_AFTER_PICK_WAIT = 0.4
_ABOARD_CONFIRM_POLL = 2.5
_ABOARD_CONFIRM_POLL_STEP = 0.35
_AFTER_SLOT = 0.45
_AFTER_CONFIRM = 0.35
_TEMPLATE_SIMILARITY = 0.90
_ABOARD_CONFIRM_SIMILARITY = 0.96
_SIX_SLOT_SIMILARITY = 0.90
_MAX_RETRY = 2
_MAX_FILTER_OPEN_RETRY = 4
_CONFIRM_INTERVAL = 0.3

# 2026 船坞 UI 改版后「确定」按钮纵向偏移，与 module/retire/dock.py 一致
FILTER_CONFIRM_OFFSET = (20, 60)

CLICK_FORMATION: Click = FA.CLICK_FORMATION
CLICK_OPEN_FLEET_MENU: Click = (240, 675)

FLEET_CLICKS: List[Click] = [
    (240, 600),
    (240, 550),
    (240, 500),
    (240, 450),
    (240, 400),
    (240, 350),
]

SHIP_SLOT_CLICKS: List[Click] = [
    (515, 470),
    (760, 410),
    (970, 375),
    (370, 320),
    (590, 275),
    (800, 240),
]

CLICK_OPEN_FILTER: Click = (1140, 30)
CLICK_FILTER_CONFIRM_FALLBACK: Click = (800, 642)
CLICK_PICK_SHIP: Click = (165, 410)
CLICK_RETURN_SLOTS: Click = (1020, 675)

FILTER_CONFIRM = DOCK_FILTER_CONFIRM

# 模板须为 1280×720 全屏截图；比对时按 area 裁切（勿用小图直存）
SIX_SLOT_OVERVIEW_AREA: Area4 = (1045, 640, 1245, 700)
SIX_SLOT_OVERVIEW_FILE = './assets/cn/proalas_fleet_swap/SixSlotOverview.png'
SIX_SLOT_OVERVIEW_CENTER: Click = (
    (SIX_SLOT_OVERVIEW_AREA[0] + SIX_SLOT_OVERVIEW_AREA[2]) // 2,
    (SIX_SLOT_OVERVIEW_AREA[1] + SIX_SLOT_OVERVIEW_AREA[3]) // 2,
)

SHIP_ABOARD_CONFIRM_AREA: Area4 = (700, 480, 880, 540)
SHIP_ABOARD_CONFIRM_FILE = './assets/cn/proalas_fleet_swap/ShipAboardConfirm.png'
SHIP_ABOARD_CONFIRM_CENTER: Click = (
    (SHIP_ABOARD_CONFIRM_AREA[0] + SHIP_ABOARD_CONFIRM_AREA[2]) // 2,
    (SHIP_ABOARD_CONFIRM_AREA[1] + SHIP_ABOARD_CONFIRM_AREA[3]) // 2,
)

# 装备页签（16576 现场截图 20,320–70,370）
EQUIP_INPUT_AREA: Area4 = (20, 320, 70, 370)
EQUIP_INPUT_FILE = './assets/cn/proalas_fleet_swap/EquipInput.png'
EQUIP_INPUT_CENTER: Click = (
    (EQUIP_INPUT_AREA[0] + EQUIP_INPUT_AREA[2]) // 2,
    (EQUIP_INPUT_AREA[1] + EQUIP_INPUT_AREA[3]) // 2,
)
_EQUIP_INPUT_SIMILARITY = 0.90

# 装备页签-选中态（16576 现场截图 20,320–70,370）
EQUIP_INPUT_YES_AREA: Area4 = (20, 320, 70, 370)
EQUIP_INPUT_YES_FILE = './assets/cn/proalas_fleet_swap/EquipInputYes.png'
EQUIP_INPUT_YES_CENTER: Click = (
    (EQUIP_INPUT_YES_AREA[0] + EQUIP_INPUT_YES_AREA[2]) // 2,
    (EQUIP_INPUT_YES_AREA[1] + EQUIP_INPUT_YES_AREA[3]) // 2,
)
_EQUIP_INPUT_YES_SIMILARITY = 0.90

# 装备识别区域 1/2/3 — 单舰详情页左侧 Tab 行（找「装备」Tab，不是五装备槽）
# 五装备槽坐标见 module.AutoEquip.assets.EQUIP_SLOT_CENTERS（共 5 个）
EquipOcrArea: dict[int, Area4] = {
    1: (20, 225, 70, 275),
    2: (20, 415, 70, 465),
    3: (20, 320, 70, 370),  # EquipInput 模板来源区域
}

EquipOcrCenter: dict[int, Click] = {
    slot: ((x1 + x2) // 2, (y1 + y2) // 2)
    for slot, (x1, y1, x2, y2) in EquipOcrArea.items()
}
