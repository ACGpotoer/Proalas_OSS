# -*- coding: utf-8 -*-
"""
UP 船坞检索：读 ProalasData.GachaUp / 全局日历 → 判断是否已拥有 → 仅写入 ProalasData（不改 Gacha 调度）。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from module.GachaUp import assets as A
from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.gacha_up_input import input_text_zh
from module.proalas.plan_quadrant_view import get_blue_payload
from module.retire.assets import DOCK_EMPTY
from module.ui.assets import GOTO_MAIN
from module.ui.page import page_main
from module.ui.ui import UI
from module.ui_white.assets import GOTO_MAIN_WHITE


class ProalasGachaCheck(UI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(self, xy: tuple[int, int], *, delay: float | None = None) -> None:
        wait = A._STEP_PAUSE if delay is None else max(float(delay), A._STEP_PAUSE)
        self.device.click_adb(*xy)
        self.device.sleep(wait)

    def _resolve_up_ships(self) -> list[str]:
        cached = deep_get(self.config.data, ['ProalasData', 'GachaUp', 'upShips'], []) or []
        ships = [str(x).strip() for x in cached if str(x).strip()]
        if ships:
            return ships
        today = datetime.now().strftime('%Y-%m-%d')
        blue = get_blue_payload(self._config_name(), today)
        gacha = blue.get('gacha') if isinstance(blue.get('gacha'), dict) else {}
        return [str(x).strip() for x in (gacha.get('up_ships') or []) if str(x).strip()]

    def _stop_if_owned(self) -> bool:
        val = deep_get(self.config.data, ['ProalasData', 'GachaUp', 'stopIfOwned'], True)
        if val is None:
            return True
        return bool(val)

    def _template_match(self, button, *, tag: str) -> bool:
        self.device.screenshot()
        matched = self.appear(button, offset=(12, 12), similarity=A._TEMPLATE_SIMILARITY)
        logger.info('GachaUp %s match=%s', tag, matched)
        return matched

    def _ensure_main(self) -> bool:
        """已在主界面即成功；ui_ensure 在已到达时返回 False，不可当作失败。"""
        if self.is_in_main():
            return True
        logger.info('GachaUp not in main, ui_goto page_main')
        try:
            self.ui_goto(page_main)
        except Exception as e:
            logger.warning('GachaUp ui_goto page_main failed: %s', e)
            return False
        return self.is_in_main()

    def _return_main(self) -> None:
        if self.is_in_main():
            return
        logger.info('GachaUp return main (GOTO_MAIN / ui_goto)')
        if self.appear_then_click(GOTO_MAIN, offset=(30, 30)):
            self.device.sleep(2.0)
        elif self.appear_then_click(GOTO_MAIN_WHITE, offset=(30, 30)):
            self.device.sleep(2.0)
        elif self.is_in_main():
            return
        else:
            try:
                self.ui_goto(page_main)
            except Exception as e:
                logger.warning('GachaUp ui_goto main fallback failed: %s, tap %s', e, A.RETURN_MAIN_CLICK)
                self._tap(A.RETURN_MAIN_CLICK, delay=2.0)
                return
        if not self.is_in_main():
            logger.warning('GachaUp return main uncertain after GOTO_MAIN')

    def _enter_dock(self) -> bool:
        for attempt in range(1, A._MAX_NAV_RETRY + 1):
            if not self._ensure_main():
                logger.warning('GachaUp ensure main failed attempt=%s', attempt)
                continue
            logger.info('GachaUp enter dock click=%s attempt=%s', A.CLICK_MAIN_TO_DOCK, attempt)
            self._tap(A.CLICK_MAIN_TO_DOCK, delay=A._AFTER_UI)
            self.device.sleep(A._AFTER_UI)
            if self._template_match(A.BOAT_AWAY_USE, tag='BoatAwayUse'):
                return True
            logger.warning('GachaUp BoatAwayUse miss attempt=%s', attempt)
            self._return_main()
        return False

    def _open_search(self) -> bool:
        has_search_yes = os.path.isfile(A.SEARCH_YES_FILE)
        for attempt in range(1, A._MAX_NAV_RETRY + 1):
            logger.info('GachaUp open search click=%s attempt=%s', A.CLICK_SEARCH_ICON, attempt)
            self._tap(A.CLICK_SEARCH_ICON, delay=A._AFTER_UI)
            self.device.sleep(A._AFTER_UI)
            if not has_search_yes:
                logger.info('GachaUp SearchYes template missing, skip verify')
                return True
            if self._template_match(A.SEARCH_YES, tag='SearchYes'):
                return True
            logger.warning('GachaUp SearchYes miss attempt=%s', attempt)
        # 模板未命中但搜索图标已点过：仍继续输入（避免「框已开却不输入」）
        logger.warning(
            'GachaUp SearchYes unverified after %s tries, proceed to input',
            A._MAX_NAV_RETRY,
        )
        return True

    def _dismiss_search_dropdown(self) -> None:
        for i in range(A.DISMISS_DROPDOWN_TIMES):
            logger.info(
                'GachaUp dismiss dropdown %s/%s %s',
                i + 1,
                A.DISMISS_DROPDOWN_TIMES,
                A.CLICK_DISMISS_DROPDOWN,
            )
            self._tap(A.CLICK_DISMISS_DROPDOWN, delay=A._AFTER_DISMISS_TAP)

    def _navigate_dock_search(self) -> bool:
        if not self._enter_dock():
            return False
        if not self._open_search():
            self._return_main()
            return False
        logger.info('GachaUp focus search input %s', A.CLICK_SEARCH_INPUT)
        self._tap(A.CLICK_SEARCH_INPUT, delay=A._AFTER_UI)
        return True

    def _search_result_not_owned(self) -> bool | None:
        self.device.screenshot()
        if os.path.isfile(A.SEARCH_BOAT_NULL_FILE):
            matched = self.appear(
                A.SEARCH_BOAT_NULL_BTN,
                offset=(20, 20),
                similarity=A.SEARCH_BOAT_NULL_THRESHOLD,
            )
            logger.info('GachaUp SearchBoatNull match=%s (True=未拥有)', matched)
            return matched
        matched = self.appear(DOCK_EMPTY, offset=(20, 20))
        logger.info('GachaUp DOCK_EMPTY fallback match=%s (True=未拥有)', matched)
        return matched

    def _check_ship(self, ship_name: str) -> dict[str, Any]:
        rep: dict[str, Any] = {'ship': ship_name, 'owned': None, 'ok': False}
        if not self._navigate_dock_search():
            rep['error'] = 'dock_nav_failed'
            self._return_main()
            return rep
        logger.info('GachaUp input ship name %r at %s', ship_name, A.CLICK_SEARCH_INPUT)
        self.device.sleep(A._STEP_PAUSE)
        self._tap(A.CLICK_SEARCH_INPUT)
        self.device.sleep(A._AFTER_INPUT_FOCUS)
        if not input_text_zh(self.device, ship_name, config=self.config):
            rep['error'] = 'input_failed'
            logger.warning('GachaUp input failed for %r', ship_name)
            self._return_main()
            return rep
        self.device.sleep(A._AFTER_INPUT_PASTE)
        self._dismiss_search_dropdown()
        self.device.sleep(A._AFTER_RESULT)
        not_owned = self._search_result_not_owned()
        if not_owned is None:
            rep['error'] = 'unknown_result'
        else:
            rep['owned'] = not not_owned
            rep['ok'] = True
        self._return_main()
        return rep

    def _write_gacha_results(
        self,
        *,
        all_owned: bool | None,
        missing: list[str],
        results: list[dict[str, Any]],
        partial: bool = False,
    ) -> None:
        name = self._config_name()
        path = filepath_config(name)
        data = read_file(path)
        if not isinstance(data, dict):
            logger.warning('GachaUp config missing %s', path)
            return
        proalas = deep_get(data, ['ProalasData'], {}) or {}
        if not isinstance(proalas, dict):
            proalas = {}
        gacha_up = dict(proalas.get('GachaUp') or {})
        gacha_up['allOwned'] = all_owned
        gacha_up['lastCheckAt'] = datetime.now().isoformat(timespec='seconds')
        gacha_up['results'] = results
        gacha_up['missing'] = list(missing)
        gacha_up['partial'] = bool(partial)
        gacha_up['recommendGacha'] = (all_owned is False and not partial and bool(missing))
        proalas['GachaUp'] = gacha_up
        deep_set(data, keys=['ProalasData'], value=proalas)
        write_file(path, data)
        logger.info(
            'GachaUp record-only allOwned=%s missing=%s partial=%s recommendGacha=%s',
            all_owned,
            missing,
            partial,
            gacha_up['recommendGacha'],
        )

    def run(
        self,
        *,
        skip_gate: bool = False,
        skip_task_delay: bool = False,
        ships_only: list[str] | None = None,
    ):
        if not skip_gate and gate_task_or_skip(self, 'ProalasGachaCheck'):
            return
        logger.hr('ProalasGachaCheck', level=1)

        if ships_only:
            up_ships = [str(x).strip() for x in ships_only if str(x).strip()]
        else:
            up_ships = self._resolve_up_ships()
        if not up_ships:
            logger.info('GachaUp no up_ships configured, skip')
            if not skip_task_delay:
                self.config.task_delay(server_update=True)
            return

        if not self._stop_if_owned():
            logger.info('GachaUp stop_if_owned=false, leave Gacha scheduler unchanged')
            if not skip_task_delay:
                self.config.task_delay(server_update=True)
            return

        self.device.stuck_record_clear()
        self.device.click_record_clear()
        self.device.screenshot()

        results: list[dict[str, Any]] = []
        missing: list[str] = []
        for name in up_ships:
            logger.info('GachaUp checking ship %r', name)
            rep = self._check_ship(name)
            results.append(rep)
            if rep.get('ok') and rep.get('owned') is False:
                missing.append(name)
            elif rep.get('ok') and rep.get('owned') is True:
                pass
            else:
                logger.warning('GachaUp inconclusive for %r: %s', name, rep.get('error'))
            if name != up_ships[-1]:
                logger.info('GachaUp pause %.1fs before next ship', A._BETWEEN_SHIPS)
                self.device.sleep(A._BETWEEN_SHIPS)

        partial = any(r.get('ok') is False or r.get('owned') is None for r in results)
        if partial:
            logger.warning('GachaUp partial failure, write partial results only')

        if ships_only:
            prior = deep_get(self.config.data, ['ProalasData', 'GachaUp', 'results'], []) or []
            merged_by_ship = {
                str(r.get('ship', '')).strip(): r
                for r in prior
                if isinstance(r, dict) and str(r.get('ship', '')).strip()
            }
            for rep in results:
                name = str(rep.get('ship', '')).strip()
                if name:
                    merged_by_ship[name] = rep
            full_up = self._resolve_up_ships()
            results = [merged_by_ship[name] for name in full_up if name in merged_by_ship]
            missing = [
                str(r.get('ship', '')).strip()
                for r in results
                if isinstance(r, dict) and r.get('ok') and r.get('owned') is False
            ]
            partial = any(r.get('ok') is False or r.get('owned') is None for r in results)

        all_owned = None if partial else (len(missing) == 0)
        self._write_gacha_results(
            all_owned=all_owned,
            missing=missing,
            results=results,
            partial=partial,
        )
        logger.info(
            'GachaUp done up=%s missing=%s partial=%s recommend=%s',
            up_ships,
            missing,
            partial,
            (not partial and bool(missing)),
        )
        if not skip_task_delay:
            self.config.task_delay(server_update=True)
