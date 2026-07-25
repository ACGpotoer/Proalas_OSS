# -*- coding: utf-8 -*-
"""
ProAlas 活动 PT 商店兑换（简化版）。

规则：
- 仅周日执行；非周日推到下个周日
- 进不去活动 PT 商店（无活动/无商店）→ 跳过，推到下个周日
- 兑换全部「价格 OCR ≠ 1」且未售罄、PT 够的商品（单价高的优先，顺手先拿贵的）
- 不做复杂优先级链 / UR 两阶段补货；多数量弹窗仍按模板点确认

涉及模板见 module/EventPtShop/assets.py 顶部清单。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from module.EventPtShop import assets as A
from module.config.deep import deep_set
from module.logger import logger
from module.proalas.auto_event_shop_config import (
    format_token_pt,
    format_token_ur_item,
    parse_shop_count,
)
from module.proalas.event_pt_shop_ocr import ItemPrice, read_item_prices, read_tokens
from module.proalas.feature_gate import gate_task_or_skip
from module.ui.ui import UI


def _weekday_cn(now: Optional[datetime] = None) -> int:
    """0=周一 … 6=周日（与 datetime.weekday 一致）。"""
    return (now or datetime.now()).weekday()


def minutes_until_next_sunday(*, from_now: Optional[datetime] = None) -> int:
    """
    距「下个周日 0 点附近」的粗略分钟数（按自然日整日推迟）。
    若今天已是周日：再推 7 天（用于「周日无店 / 已跑完」）。
    """
    now = from_now or datetime.now()
    wd = now.weekday()
    if wd == 6:
        return 7 * 1440
    return (6 - wd) * 1440


class ProalasAutoEventShop(UI):
    exchange_count: int = 0

    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(self, xy: tuple[int, int], *, delay: float = A._AFTER_CLICK) -> None:
        self.device.click_adb(*xy)
        self.device.sleep(max(float(delay), A._MIN_CLICK_INTERVAL))

    def _delay_to_next_sunday(self, reason: str) -> None:
        minute = minutes_until_next_sunday()
        logger.info('EventShop %s → 推迟约 %s 分钟（下周日）', reason, minute)
        self.config.task_delay(minute=minute)

    def _sync_token_display(self, *, ur_item: Optional[int], pt: Optional[int]) -> None:
        ur_text = format_token_ur_item(ur_item)
        pt_text = format_token_pt(pt)
        deep_set(
            self.config.data,
            ('ProalasAutoEventShop', 'ProalasAutoEventShop', 'TokenUrItem'),
            ur_text,
        )
        deep_set(
            self.config.data,
            ('ProalasAutoEventShop', 'ProalasAutoEventShop', 'TokenPt'),
            pt_text,
        )
        self.config.ProalasAutoEventShop_TokenUrItem = ur_text
        self.config.ProalasAutoEventShop_TokenPt = pt_text
        logger.info('EventShop tokens display UR=%s PT=%s', ur_text, pt_text)

    def _read_tokens(self) -> tuple[Optional[int], Optional[int]]:
        self.device.screenshot()
        return read_tokens(self.device.image)

    def _read_items(self) -> list[ItemPrice]:
        self.device.screenshot()
        return read_item_prices(self.device.image)

    def _in_shop_list(self) -> bool:
        return self.appear(
            A.INTO_PT_SHOP,
            offset=(15, 15),
            similarity=A._TEMPLATE_SIMILARITY,
        )

    def _is_sold_out(self, row: int, slot: int) -> bool:
        area = A.sold_out_area(row, slot)
        btn = A.sold_out_button(area)
        return self.appear(btn, offset=(12, 12), similarity=A._TEMPLATE_SIMILARITY)

    def _is_double_buy_dialog(self) -> bool:
        return self.appear(
            A.DOUBLE_BUY,
            offset=(15, 15),
            similarity=A._TEMPLATE_SIMILARITY,
        )

    def _skip_animation(self) -> None:
        for i in range(A._ANIMATION_SKIP_MAX):
            self._tap(A.SKIP_ANIMATION, delay=A._ANIMATION_INTERVAL)
            self.device.screenshot()
            if self._in_shop_list():
                logger.info('EventShop 动画跳过完成 step=%s', i + 1)
                return
        logger.warning('EventShop 动画跳过后仍未回到商店列表')

    def _confirm_exchange(self) -> None:
        self.device.screenshot()
        if self._is_double_buy_dialog():
            self._tap(A.CONFIRM_MULTI, delay=A._AFTER_CONFIRM)
        else:
            self._tap(A.CONFIRM_SINGLE, delay=A._AFTER_CONFIRM)
        self._skip_animation()

    def _navigate_to_shop(self) -> bool:
        self.ui_goto_main()
        self._tap(A.CLICK_EVENT_ENTRY, delay=A._AFTER_NAV)
        self.device.screenshot()
        if not self._in_shop_list():
            logger.warning('EventShop IntoPTShop 未匹配，无活动商店或界面不符')
            return False
        self._tap(A.CLICK_INTO_PT_TAB)
        self.device.sleep(A._AFTER_CLICK)
        self.device.screenshot()
        if not self.appear(
            A.PT_SHOP,
            offset=(15, 15),
            similarity=A._TEMPLATE_SIMILARITY,
        ):
            logger.warning('EventShop PTshop 未匹配，无 PT 商店页')
            return False
        self._tap(A.pt_shop_center())
        self.device.sleep(A._AFTER_CLICK)
        return True

    def _refresh_shop_tabs(self) -> None:
        logger.info('EventShop 刷新商店 Tab（每 %s 次）', A.REFRESH_EVERY_N)
        self._tap(A.SHOP_TAB_A)
        self.device.sleep(1.0)
        self._tap(A.SHOP_TAB_B)
        self.device.sleep(A._AFTER_CLICK)

    def _maybe_refresh(self) -> None:
        if self.exchange_count > 0 and self.exchange_count % A.REFRESH_EVERY_N == 0:
            self._refresh_shop_tabs()

    def _buy_item(self, item: ItemPrice) -> bool:
        ur_before, pt_before = self._read_tokens()
        logger.info(
            'EventShop 兑换 row=%s slot=%s price=%s',
            item.row,
            item.slot,
            item.value,
        )
        self._tap((item.x, item.y), delay=A._AFTER_PRICE)
        self._confirm_exchange()
        ur_after, pt_after = self._read_tokens()
        self._sync_token_display(ur_item=ur_after, pt=pt_after)

        success = (
            pt_before is not None
            and pt_after is not None
            and pt_after < pt_before
        )
        # UR 货币商品：PT 可能不变，UR 减少也算成功
        if not success and ur_before is not None and ur_after is not None:
            success = ur_after < ur_before

        if success:
            self.exchange_count += 1
            self._maybe_refresh()
            logger.info(
                'EventShop 兑换成功 UR %s->%s PT %s->%s',
                ur_before,
                ur_after,
                pt_before,
                pt_after,
            )
            return True

        logger.warning(
            'EventShop 兑换可能失败/售罄 row=%s slot=%s price=%s',
            item.row,
            item.slot,
            item.value,
        )
        return False

    def _should_skip(self, item: ItemPrice, pt: Optional[int]) -> bool:
        if item.value is None:
            return True
        if item.value == A.TRAP_PRICE:
            logger.info('EventShop 跳过单价=1 row=%s slot=%s', item.row, item.slot)
            return True
        if self._is_sold_out(item.row, item.slot):
            logger.info('EventShop 已售罄 row=%s slot=%s', item.row, item.slot)
            return True
        if pt is not None and pt < item.value:
            return True
        return False

    def _pick_next(self, items: list[ItemPrice], pt: Optional[int]) -> Optional[ItemPrice]:
        """单价从高到低，同价按格子顺序。"""
        candidates = [
            i for i in items
            if not self._should_skip(i, pt)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda i: (-int(i.value or 0), i.row, i.slot))
        return candidates[0]

    def _run_exchange_loop(self) -> None:
        idle_rounds = 0
        while True:
            ur, pt = self._read_tokens()
            self._sync_token_display(ur_item=ur, pt=pt)
            items = self._read_items()
            target = self._pick_next(items, pt)
            if target is None:
                idle_rounds += 1
                if idle_rounds >= 2:
                    logger.info('EventShop 无可兑换商品，结束')
                    break
                # 刷新后再扫一轮，避免界面未刷完误判
                self._refresh_shop_tabs()
                continue
            idle_rounds = 0
            if not self._buy_item(target):
                # 单格失败则跳过该格后续：刷新后继续；连续失败过多则结束
                idle_rounds += 1
                if idle_rounds >= 5:
                    logger.warning('EventShop 连续兑换失败过多，结束')
                    break

    def run(self):
        if gate_task_or_skip(self, 'ProalasAutoEventShop'):
            return
        logger.hr('ProalasAutoEventShop', level=1)
        self.exchange_count = 0

        if _weekday_cn() != 6:
            self.config.save()
            self._delay_to_next_sunday('非周日')
            return

        shop_count = parse_shop_count(self.config)
        logger.info(
            'EventShop 简化兑换：周日全换非1商品 shops_cfg=%s（>1 暂无双店模板，仅第一家）',
            shop_count,
        )
        if shop_count > 1:
            logger.warning(
                'EventShop ShopCount=%s 尚无第二/三店切换模板，仍只处理当前 PT 商店',
                shop_count,
            )

        if not self._navigate_to_shop():
            self.config.save()
            self._delay_to_next_sunday('无活动商店')
            return

        self._run_exchange_loop()

        ur_val, pt_val = self._read_tokens()
        self._sync_token_display(ur_item=ur_val, pt=pt_val)
        logger.info('EventShop 完成 exchanges=%s', self.exchange_count)
        self.config.save()
        self._delay_to_next_sunday('本周已兑完')
