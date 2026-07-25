# -*- coding: utf-8 -*-
"""编队采集固定坐标（来自 ProAlas getFleetStrength/assets.py）。"""
from __future__ import annotations

CLICK_FORMATION = (1063, 512)
CLICK_DETAILS = (951, 679)
CLICK_RETURN_MAIN = (1220, 30)

TEAM_SWITCH_CLICKS = [
    [(241, 676), (244, 604)],
    [(242, 673), (258, 553)],
    [(238, 673), (271, 502)],
    [(241, 673), (271, 452)],
    [(239, 672), (234, 393)],
    [(242, 673), (245, 341)],
]

POWER_MIN = 100
POWER_MAX = 9999

# 单舰详情页综合性能（粗体数字，右上角）
SHIP_POWER_BOLD_AREA = (1140, 220, 1250, 280)

# 编队详情页：点击各槽位进入单舰界面（slot 1–6）
SHIP_CLICKS = [
    (140, 470),
    (330, 470),
    (510, 470),
    (770, 470),
    (950, 470),
    (1140, 470),
]

# 单舰界面 → 返回编队详情页
CLICK_RETURN_DETAIL = (50, 50)

# 编队详情页舰名 OCR 区域
SHIP_SLOTS = [
    {'slot': 1, 'name': (68, 464, 214, 491)},
    {'slot': 2, 'name': (258, 462, 400, 486)},
    {'slot': 3, 'name': (458, 462, 586, 486)},
    {'slot': 4, 'name': (718, 464, 823, 490)},
    {'slot': 5, 'name': (898, 462, 1014, 486)},
    {'slot': 6, 'name': (1076, 459, 1206, 486)},
]

MIN_CLICK_INTERVAL = 1.0
_AFTER_CLICK = 1.0
_AFTER_SWITCH = 1.0
_AFTER_DETAILS = 1.2
_AFTER_SHIP = 1.0
_AFTER_RETURN_DETAIL = 1.0

# 多实例并发时 UI 响应偏慢，在上方基准上统一 +3s
_CLICK_DELAY_EXTRA = 3.0
MIN_CLICK_INTERVAL += _CLICK_DELAY_EXTRA
_AFTER_CLICK += _CLICK_DELAY_EXTRA
_AFTER_SWITCH += _CLICK_DELAY_EXTRA
_AFTER_DETAILS += _CLICK_DELAY_EXTRA
_AFTER_SHIP += _CLICK_DELAY_EXTRA
_AFTER_RETURN_DETAIL += _CLICK_DELAY_EXTRA
