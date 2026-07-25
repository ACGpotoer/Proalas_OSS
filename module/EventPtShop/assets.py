# -*- coding: utf-8 -*-
"""活动 PT 商店模板与 OCR 区域（简化兑换用）。

════════════════════════════════════════════════════════
模板图像清单（assets/cn/EventPtShop/）— 缺则标注「无文件」
════════════════════════════════════════════════════════

【当前代码真实引用】
1. IntoPTShop.png
   用途：主界面点活动后，判断侧栏「是否已有活动商店入口」
   缺了怎么办：导航失败 → 视为无活动商店，周日推迟下周

2. PTshop.png
   用途：侧栏点进商店区后，确认「PT 商店」页签/按钮存在
   缺了怎么办：进不去 PT 店 → 同上跳过

3. SoldOut.png
   用途：各商品格「已售罄」遮罩匹配（运行时把同一模板套到 2×5 格区域）
   缺了/不准：可能对售罄格反复点，依赖兑换后 PT/UR 未变才判失败

4. DoubleBuy.png
   用途：多数量兑换弹窗特征（有加减数量时走下方确认坐标）
   缺了怎么办：会走「单次确认」坐标，数量弹窗可能点空

【目录里有、代码未引用】
5. IntoPTShop_crop.png / PTshop_crop.png
   用途：历史裁切调试图，运行时不用

【明确缺失（简化后仍缺）— 需要你补图才做得了】
6. 双活动 / 第二家 PT 商店切换
   现状：ShopCount=2/3 仅警告；无「第二店 Tab / 店名」模板
   建议：截第二店选中/未选中（或左右店切换钮）各一张再接线

7. 活动入口按钮本身
   现状：固定坐标 CLICK_EVENT_ENTRY=(910,30)，无模板
   风险：不同活动入口位置变了会点偏（靠 IntoPTShop 兜底失败）

8. 单次 / 多次确认钮本体
   现状：CONFIRM_SINGLE / CONFIRM_MULTI 为固定坐标，无独立确认模板
   风险：弹窗改版后点偏（DoubleBuy 只区分弹窗类型）

9. 单价=1 的「陷阱」商品
   现状：靠 OCR 价格==1 跳过，无专用模板（一般够用）
════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Tuple

from module.base.button import Button

Area4 = Tuple[int, int, int, int]
Click = Tuple[int, int]

# ---------- 导航与兑换点击 ----------
CLICK_EVENT_ENTRY: Click = (910, 30)
CLICK_INTO_PT_TAB: Click = (100, 390)
CLICK_QTY_PLUS: Click = (720, 330)
CONFIRM_MULTI: Click = (790, 660)
CONFIRM_SINGLE: Click = (790, 515)
SKIP_ANIMATION: Click = (980, 670)
SHOP_TAB_A: Click = (90, 450)
SHOP_TAB_B: Click = (90, 550)

# 简化策略：不再用 PT 低水位停兑；保留常量仅兼容旧引用
PT_STOP_THRESHOLD = 0
URITEM_UNIT_PT = 150
UR_TARGETS = (200, 300)
TRAP_PRICE = 1
REFRESH_EVERY_N = 3
PAUSE_WHEN_LOW_PT_MINUTES = 1440

_AFTER_CLICK = 0.5
_AFTER_NAV = 2.0
_AFTER_PRICE = 1.0
_AFTER_CONFIRM = 1.0
_ANIMATION_INTERVAL = 1.0
_ANIMATION_SKIP_MAX = 4
_MIN_CLICK_INTERVAL = 0.3

INTO_PT_SHOP_AREA: Area4 = (50, 370, 160, 400)

INTO_PT_SHOP = Button(
    area={'cn': INTO_PT_SHOP_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': INTO_PT_SHOP_AREA},
    file={'cn': './assets/cn/EventPtShop/IntoPTShop.png'},
    name='IntoPTShop',
)

PT_SHOP_AREA: Area4 = (45, 530, 140, 560)

PT_SHOP = Button(
    area={'cn': PT_SHOP_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': PT_SHOP_AREA},
    file={'cn': './assets/cn/EventPtShop/PTshop.png'},
    name='PTshop',
)

# 已售罄 overlay（模板截取参考：第 1 行第 1 格；运行时在各商品格内匹配）
SOLD_OUT_AREA: Area4 = (260, 250, 335, 320)

SOLD_OUT = Button(
    area={'cn': SOLD_OUT_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': SOLD_OUT_AREA},
    file={'cn': './assets/cn/EventPtShop/SoldOut.png'},
    name='SoldOut',
)

# 多数量兑换确认弹窗特征（数量加减 + 确认区局部）
DOUBLE_BUY_AREA: Area4 = (750, 600, 840, 660)

DOUBLE_BUY = Button(
    area={'cn': DOUBLE_BUY_AREA},
    color={'cn': (128, 128, 128)},
    button={'cn': DOUBLE_BUY_AREA},
    file={'cn': './assets/cn/EventPtShop/DoubleBuy.png'},
    name='DoubleBuy',
)

# 信物数量 OCR
TOKEN_UR_ITEM_AREA: Area4 = (860, 160, 930, 190)
TOKEN_PT_AREA: Area4 = (980, 160, 1060, 190)

# 商品行（全条带，调试用）
ITEM_ROW_1_AREA: Area4 = (240, 360, 1040, 390)
ITEM_ROW_2_AREA: Area4 = (240, 580, 1040, 610)

# 商品价格 OCR 子区域（橙色按钮白字）
ITEM_ROW_1_PRICE_AREAS: Tuple[Area4, ...] = (
    (288, 360, 360, 390),
    (432, 360, 504, 390),
    (600, 360, 672, 390),
    (792, 360, 864, 390),
    (936, 360, 1008, 390),
)
ITEM_ROW_2_PRICE_AREAS: Tuple[Area4, ...] = (
    (288, 580, 360, 610),
    (456, 580, 528, 610),
    (624, 580, 696, 610),
    (792, 580, 864, 610),
    (960, 580, 1032, 610),
)

ITEM_PRICE_AREAS: Tuple[Tuple[Area4, ...], ...] = (
    ITEM_ROW_1_PRICE_AREAS,
    ITEM_ROW_2_PRICE_AREAS,
)

_SOLD_OUT_W = 75
_SOLD_OUT_H = 70
_SOLD_OUT_X_OFFSET = -28
_ROW_SOLD_OUT_Y = (250, 470)


def _build_sold_out_slot_areas() -> Tuple[Tuple[Area4, ...], ...]:
    rows = []
    for row_idx, price_row in enumerate(ITEM_PRICE_AREAS):
        y1 = _ROW_SOLD_OUT_Y[row_idx]
        y2 = y1 + _SOLD_OUT_H
        slot_areas = []
        for px1, _py1, _px2, _py2 in price_row:
            x1 = px1 + _SOLD_OUT_X_OFFSET
            slot_areas.append((x1, y1, x1 + _SOLD_OUT_W, y2))
        rows.append(tuple(slot_areas))
    return tuple(rows)


SOLD_OUT_SLOT_AREAS = _build_sold_out_slot_areas()

_TEMPLATE_SIMILARITY = 0.85
_SOLD_OUT_FILE = './assets/cn/EventPtShop/SoldOut.png'
_DOUBLE_BUY_FILE = './assets/cn/EventPtShop/DoubleBuy.png'


def pt_shop_center() -> Click:
    x1, y1, x2, y2 = PT_SHOP_AREA
    return (x1 + x2) // 2, (y1 + y2) // 2


def sold_out_button(area: Area4) -> Button:
    return Button(
        area={'cn': area},
        color={'cn': (128, 128, 128)},
        button={'cn': area},
        file={'cn': _SOLD_OUT_FILE},
        name='SoldOut',
    )


def sold_out_area(row: int, slot: int) -> Area4:
    return SOLD_OUT_SLOT_AREAS[row - 1][slot - 1]
