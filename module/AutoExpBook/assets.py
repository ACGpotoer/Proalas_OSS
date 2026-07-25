# -*- coding: utf-8 -*-
"""自动使用经验书 — 船坞喂食流程坐标（1280×720）。"""
from __future__ import annotations

from typing import Tuple

Click = Tuple[int, int]

_AFTER_TAP = 0.45
_AFTER_FILTER = 0.35
_AFTER_FEED = 0.6
_AFTER_BACK = 0.5
_MIN_CLICK_INTERVAL = 0.35
_ABOARD_CONFIRM_POLL = 2.0
_ABOARD_CONFIRM_POLL_STEP = 0.25

CLICK_SELECT_SHIP: Click = (320, 210)
CLICK_PICK_EXP_BOOK: Click = (860, 290)
CLICK_FEED_CONFIRM: Click = (670, 550)
CLICK_FEED_APPLY: Click = (880, 550)
CLICK_BACK_DETAIL: Click = (50, 50)

FEED_CLICKS: tuple[Click, ...] = (
    CLICK_SELECT_SHIP,
    CLICK_PICK_EXP_BOOK,
    CLICK_FEED_CONFIRM,
    CLICK_FEED_APPLY,
)
