# -*- coding: utf-8 -*-
"""装备 UI：OCR、导航、NullEquipment 模板与五槽位坐标。"""
from __future__ import annotations

from module.base.button import Button
from module.ocr.ocr import DigitCounter, DigitCounterYuv

# ── 空装备槽：整图 80×80 仅作采样参考；比对用中心白十字（见 equip_slot_match.py）──
NULL_EQUIPMENT_AREA = (870, 515, 950, 595)

NULL_EQUIPMENT = Button(
    area={'cn': NULL_EQUIPMENT_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': NULL_EQUIPMENT_AREA},
    file={'cn': './assets/cn/AutoEquip/NullEquipment.png'},
    name='NullEquipment',
)

# 装备更换列表为空：「没有可替换的装备」条带（280,90）→（1180,240），900×150
NULL_ANY_EQUIPMENT_AREA = (280, 90, 1180, 240)

NULL_ANY_EQUIPMENT = Button(
    area={'cn': NULL_ANY_EQUIPMENT_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': NULL_ANY_EQUIPMENT_AREA},
    file={'cn': './assets/cn/AutoEquip/NullAnyEquipment.png'},
    name='NullAnyEquipment',
)

# 列表空态 TM 阈值（cv2 整图比对；模板与截图均 BGR）
NULL_ANY_EQUIPMENT_TM_MIN = 0.70

# 五装备槽中心（±40px → 80×80 检测区）
EQUIP_SLOT_RADIUS = 40
EQUIP_SLOT_CENTERS: list[tuple[int, int]] = [
    (915, 195),   # slot1 后排上
    (950, 380),   # slot2 后排中
    (910, 555),   # slot3 后排下（模板采样槽）
    (170, 295),   # slot4 前排上
    (170, 480),   # slot5 前排下
]

# ── 装备仓库 OCR ──
OCR_EQUIP_WAREHOUSE_AREA = (170, 660, 300, 700)

OCR_EQUIP_WAREHOUSE = DigitCounter(
    OCR_EQUIP_WAREHOUSE_AREA,
    letter=(255, 255, 255),
    threshold=128,
    name='OCR_EQUIP_WAREHOUSE',
)
OCR_EQUIP_WAREHOUSE_YUV = DigitCounterYuv(
    OCR_EQUIP_WAREHOUSE_AREA,
    letter=(255, 255, 255),
    threshold=128,
    name='OCR_EQUIP_WAREHOUSE_YUV',
)

# ── 单舰战力页 → 装备五槽 ──
# 左侧竖栏 OCR「装备」（含图标下文字，宽 175px）
OCR_SHIP_TAB_AREA = (5, 115, 180, 650)
OCR_SHIP_TAB_TEXT = '装备'
OCR_SHIP_TAB_ROWS = 3
# OCR 失败时点击「装备」Tab 中心（详情页左栏第二项）
CLICK_TAB_EQUIP_FALLBACK = (55, 288)

CLICK_OPEN_EQUIP_LIST_FILTER = (45, 570)
CLICK_PICK_CANDIDATE_EQUIP = (200, 160)
CLICK_CONFIRM_EQUIP_AND_BACK = (880, 650)
# 左上角返回：(55,55) 与编队 (50,50) 等价，同一按钮，每次只退一层
CLICK_BACK = (55, 55)

WAIT_AFTER_TAB = 1.0
WAIT_AFTER_SLOT = 1.0
WAIT_AFTER_FILTER = 1.0
WAIT_AFTER_PICK = 1.0
# 空槽装配成功：(880,650) 已自动回五槽，仅 wait 1s，不再点返回
WAIT_AFTER_EQUIP_SUCCESS = 1.0
# 空槽无可替换：点两次 CLICK_BACK，间隔 2s
WAIT_BETWEEN_RETURN_FAIL = 2.0

CLICK_OPEN_EQUIP_FROM_MAIN: tuple[int, int] = (410, 680)
CLICK_OPEN_WAREHOUSE: tuple[int, int] = (1020, 680)
CLICK_RETURN_MAIN: tuple[int, int] = (1230, 30)

MIN_CLICK_INTERVAL = 1.0
AFTER_CLICK = 1.2
AFTER_WAREHOUSE_LOAD = 3.0
SAME_POS_EXTRA_DELAY = 1.5

CLICKS_AUTO_EQUIP: list[tuple[int, int]] = []
CLICKS_REPLACE_SURPLUS_PURPLE: list[tuple[int, int]] = []
CLICKS_SIMPLE_CRAFT: list[tuple[int, int]] = []

CLICKS_OPEN_WAREHOUSE: list[tuple[int, int]] = [
    CLICK_OPEN_EQUIP_FROM_MAIN,
    CLICK_OPEN_WAREHOUSE,
]
