# -*- coding: utf-8 -*-
"""科研补齐 · 开发船坞扫描：开始/进行中/完成研究、任务能交就交、换队。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from module.CollectionFill import assets as A
from module.base.timer import Timer
from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.research_faction import (
    apply_level_team_faction,
    ocr_research_faction_panel,
)
from module.proalas.research_name_ocr import ocr_research_ship_name
from module.proalas.research_task_policy import research_task_submit_due
from module.proalas.research_task_submit import (
    ResearchTaskSubmit,
    apply_task_submit_result_to_research,
)
from module.shipyard.assets import SHIPYARD_CONFIRM_DEV, SHIPYARD_CONFIRM_FATE
from module.shipyard.ui import ShipyardUI
from module.shipyard.ui_globals import SHIPYARD_FACE_GRID
from module.ui.page import page_shipyard


class ProalasResearchScan(ShipyardUI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _ocr_ship_name(self) -> str:
        return ocr_research_ship_name(self.device.image)

    def _is_research_running(self) -> bool:
        """仅「研究进行中...」模板：当前正在做的科研。"""
        return self.match_template_color(
            A.START_SCIENCE_BOAT_RUNNING,
            offset=A.TEMPLATE_OFFSET,
            similarity=A.TEMPLATE_SIMILARITY,
        )

    def _is_research_end(self) -> bool:
        """「完成研究」橙钮：任务已齐、待点结束。"""
        return self.match_template_color(
            A.END_SCIENCE_BOAT,
            offset=A.TEMPLATE_OFFSET,
            similarity=A.TEMPLATE_SIMILARITY,
        )

    def _detect_status(self) -> str:
        """
        Returns:
            'end' | 'running' | 'start' | 'completed'
        优先级：完成研究 > 进行中 > 开始研究 > 已结束。
        """
        if self._is_research_end():
            return 'end'
        if self._is_research_running():
            return 'running'
        if self.match_template_color(
            A.START_SCIENCE_BOAT,
            offset=A.TEMPLATE_OFFSET,
            similarity=A.TEMPLATE_SIMILARITY,
        ):
            return 'start'
        return 'completed'

    def _sync_active_research_faction(self, *, series: int, index: int, ship: str) -> dict | None:
        """当前科研船：OCR 右侧 xx主力/先锋 → 写入自动换队 LevelTeamFaction。"""
        info = ocr_research_faction_panel(self.device.image)
        if not info:
            logger.warning(
                'ResearchScan active research faction OCR miss series=%s index=%s ship=%r',
                series,
                index,
                ship,
            )
            return None
        key = str(info.get('key') or '')
        if not key:
            return None
        apply_level_team_faction(self._config_name(), key)
        logger.info(
            'ResearchScan active research series=%s index=%s ship=%r faction=%s/%s %s',
            series,
            index,
            ship,
            info.get('short'),
            info.get('role'),
            info.get('labelZh'),
        )
        return info

    def _face_nav_info(self):
        return self._shipyard_bottom_navbar.get_info(main=self)

    def _wait_after_series(self, timeout: float = 4.0) -> None:
        """系列切换后稍等页面稳定（8 期等脸图色可能偏，不强制要求 nav 高亮）。"""
        timer = Timer(timeout).start()
        skip = True
        while 1:
            if skip:
                skip = False
            else:
                self.device.screenshot()
            if self._shipyard_in_ui():
                active, minimum, maximum = self._face_nav_info()
                if active is not None and minimum is not None:
                    logger.info(
                        'ResearchScan face nav ready active=%s range=(%s,%s)',
                        active,
                        minimum,
                        maximum,
                    )
                    return
            if timer.reached():
                logger.warning(
                    'ResearchScan face nav color not ready — fallback to fixed slot clicks'
                )
                return

    def _focus_ship_fixed(self, index: int, *, settle: float = 1.2) -> bool:
        """
        按固定从左第 index 槽点击（1-based）。
        3 期起每期固定 5 槽、位置可沿用；不依赖底部高亮识别（避免 8/9 期卡死）。
        """
        if index <= 0 or index > len(SHIPYARD_FACE_GRID.buttons):
            return False
        target = index - 1
        button = SHIPYARD_FACE_GRID.buttons[target]

        self.device.screenshot()
        active, _, _ = self._face_nav_info()
        if active == target and self._shipyard_in_ui():
            return True

        logger.info('ResearchScan focus fixed slot index=%s (grid=%s)', index, target)
        self.device.click(button)
        confirm = Timer(settle, count=2).start()
        fail = Timer(settle + 2.5).start()
        while 1:
            self.device.screenshot()
            if not self._shipyard_in_ui():
                if fail.reached():
                    logger.warning('ResearchScan left shipyard after click index=%s', index)
                    return False
                continue
            active, _, _ = self._face_nav_info()
            # 高亮识别成功最好；失败也承认（部分期导航色不一致）
            if active == target:
                if confirm.reached():
                    return True
            elif confirm.reached():
                logger.info(
                    'ResearchScan focus index=%s without nav highlight (active=%s) — accept',
                    index,
                    active,
                )
                return True
            if fail.reached():
                # 仍在船坞则收下，继续扫下一艘，勿整期 abort
                ok = self._shipyard_in_ui()
                logger.warning(
                    'ResearchScan focus soft-timeout index=%s in_ui=%s — continue',
                    index,
                    ok,
                )
                return ok
        return False

    @staticmethod
    def _ship_name_match(expect: str, got: str) -> bool:
        """船名比对：空期望视为不校验；支持互相包含（OCR 少字）。"""
        a = (expect or '').strip()
        b = (got or '').strip()
        if not a:
            return True
        if not b:
            return False
        return a == b or a in b or b in a

    def _relocate_commit(
        self,
        index: int,
        name: str,
        status: str,
    ) -> tuple[int | None, str, str]:
        """
        选中目标槽后必须再点一次聚焦：遍历扫槽会停在最后一艘，
        若不回点，后续任务/阵营会误扫到别的船（如暴风雨）。
        """
        logger.info(
            'ResearchScan relocate commit focus index=%s ship=%r status=%s',
            index,
            name,
            status,
        )
        if not self._focus_ship_fixed(index, settle=1.0):
            logger.warning('ResearchScan relocate commit focus failed index=%s', index)
            return None, '', ''
        self.device.screenshot()
        got = self._detect_status()
        if status and got and got != status:
            logger.warning(
                'ResearchScan relocate commit status drift expect=%s got=%s',
                status,
                got,
            )
        return index, name, got or status

    def _relocate_ship_in_series(
        self,
        series: int,
        *,
        expect_ship: str = '',
        want_status: str | None = None,
    ) -> tuple[int | None, str, str]:
        """
        同期槽位会因「开研 / 完成研究」重排：遍历固定槽，按状态/船名重新定位。

        Args:
            series: 期数
            expect_ship: 期望船名（可空=不校验名）
            want_status: 期望状态，如 'running' / 'start' / 'end'；None=任意

        Returns:
            (1-based index, ocr_name, status)；找不到则 (None, '', '')
            成功时保证当前 UI 已聚焦到该槽（不会停在扫过的其它船）。
        """
        max_index = A.max_ship_index(series)
        logger.info(
            'ResearchScan relocate series=%s expect=%r status=%s slots=1..%s',
            series,
            expect_ship,
            want_status,
            max_index,
        )

        # 当前页已是目标时，尽量用底部高亮直接拿 index
        self.device.screenshot()
        cur_status = self._detect_status()
        if want_status is None or cur_status == want_status:
            cur_name = self._ocr_ship_name() if expect_ship else ''
            name_ok = (not expect_ship) or self._ship_name_match(expect_ship, cur_name)
            if name_ok:
                active, _, _ = self._face_nav_info()
                if active is not None:
                    idx = active + 1
                    name = cur_name or expect_ship
                    logger.info(
                        'ResearchScan relocate hit current index=%s ship=%r status=%s',
                        idx,
                        name,
                        cur_status,
                    )
                    return self._relocate_commit(idx, name, cur_status)
                logger.info('ResearchScan relocate current OK but nav unknown — scan slots')

        candidates: list[tuple[int, str, str]] = []
        for index in range(1, max_index + 1):
            if not self._focus_ship_fixed(index, settle=0.9):
                continue
            status = self._detect_status()
            if want_status is not None and status != want_status:
                continue
            name = self._ocr_ship_name() or ''
            logger.info(
                'ResearchScan relocate candidate index=%s ship=%r status=%s',
                index,
                name,
                status,
            )
            # 有期望船名：命中即停，避免继续扫到暴风雨后停在错船
            if expect_ship and self._ship_name_match(expect_ship, name):
                return self._relocate_commit(index, name or expect_ship, status)
            # 无船名、只要唯一状态（如 running）：第一艘即目标
            if not expect_ship and want_status is not None:
                return self._relocate_commit(index, name, status)
            candidates.append((index, name, status))

        if not candidates:
            logger.warning(
                'ResearchScan relocate miss series=%s expect=%r status=%s',
                series,
                expect_ship,
                want_status,
            )
            return None, '', ''

        # expect_ship 未命中（OCR 漂移）时退回第一候选，仍须 commit 聚焦
        logger.warning(
            'ResearchScan relocate name miss expect=%r candidates=%s — fallback first',
            expect_ship,
            [(i, n, s) for i, n, s in candidates],
        )
        index, name, status = candidates[0]
        return self._relocate_commit(index, name, status)

    def _scan_ship(self, series: int, index: int) -> dict[str, Any]:
        # 切船后 UI 可能未刷新「开始研究」→ 误判 completed；短等 + 完成态复检
        self.device.sleep(A.RESEARCH_FOCUS_SETTLE_EXTRA)
        self.device.screenshot()
        status = self._detect_status()
        if status == 'completed':
            self.device.sleep(A.RESEARCH_STATUS_RETRY_WAIT)
            self.device.screenshot()
            status2 = self._detect_status()
            if status2 != status:
                logger.info(
                    'ResearchScan status retry series=%s index=%s %s -> %s',
                    series,
                    index,
                    status,
                    status2,
                )
                status = status2
        ship = ''
        label = ''
        faction_info = None
        incomplete = status in ('start', 'running', 'end')
        if incomplete:
            ship = self._ocr_ship_name()
            # OCR 失败仍记录为未完成（第 N 艘），避免漏船；EMPTY 误报可后续收紧
            label = A.incomplete_label(series, ship, index=index)
            if not ship:
                logger.warning(
                    'ResearchScan incomplete name empty series=%s index=%s status=%s label=%s',
                    series,
                    index,
                    status,
                    label,
                )
            else:
                logger.info(
                    'ResearchScan incomplete series=%s index=%s status=%s ship=%r label=%s',
                    series,
                    index,
                    status,
                    ship,
                    label,
                )
            # 仅「研究进行中」才同步练级队阵营（自动配队 3/4）
            if status == 'running':
                faction_info = self._sync_active_research_faction(
                    series=series,
                    index=index,
                    ship=ship,
                )
        else:
            logger.info(
                'ResearchScan completed series=%s index=%s',
                series,
                index,
            )
        row = {
            'series': series,
            'index': index,
            'ship': ship,
            'label': label,
            'status': status,
            'completed': not incomplete,
        }
        if faction_info:
            row['factionKey'] = faction_info.get('key')
            row['factionLabel'] = faction_info.get('labelZh')
            row['factionRole'] = faction_info.get('role')
            row['factionShort'] = faction_info.get('short')
        return row

    def _write_results(
        self,
        *,
        results: list[dict[str, Any]],
        incomplete_labels: list[str],
        errors: list[str],
        task_submit_summary: dict[str, Any] | None = None,
        force_next_task_submit: bool = False,
        next_research_scan_at: datetime | None = None,
        clear_next_research_scan_at: bool = False,
    ) -> str:
        name = self._config_name()
        path = filepath_config(name)
        data = read_file(path)
        if not isinstance(data, dict):
            logger.warning('ResearchScan config missing %s', path)
            return ''

        now = datetime.now().isoformat(timespec='seconds')
        first_incomplete = next(
            (r for r in results if isinstance(r, dict) and r.get('completed') is False),
            None,
        )
        active_running = next(
            (
                r for r in results
                if isinstance(r, dict) and r.get('status') == 'running'
            ),
            None,
        )
        active_end = next(
            (
                r for r in results
                if isinstance(r, dict) and r.get('status') == 'end'
            ),
            None,
        )
        active = active_running or active_end

        proalas = deep_get(data, ['ProalasData'], {}) or {}
        if not isinstance(proalas, dict):
            proalas = {}
        fill = dict(proalas.get('CollectionFill') or {})
        research = dict(fill.get('research') or {})
        phase = ''
        if active_running:
            phase = 'RUNNING'
        elif active_end:
            phase = 'END'
        elif first_incomplete and str(first_incomplete.get('status') or '') == 'start':
            phase = 'START'
        # 底栏 8 格若有 RY，可作为更细进度文案（可选，无则仅 phase）
        stage_hint = None
        if active_running:
            stage_hint = '进行中'
        elif active_end:
            stage_hint = '可点完成'
        research.update({
            'incompleteCount': len(incomplete_labels),
            'incompleteLabels': list(incomplete_labels),
            'results': results,
            'errors': list(errors),
            'updatedAt': now,
            'lastCheckAt': now,
            'lastScanAt': now,
            'currentSeries': (
                active['series'] if active
                else (first_incomplete['series'] if first_incomplete else None)
            ),
            'currentIndex': (
                active['index'] if active
                else (first_incomplete['index'] if first_incomplete else None)
            ),
            'currentShip': (
                (active.get('ship') or '') if active
                else ((first_incomplete.get('ship') or '') if first_incomplete else '')
            ),
            'currentStage': stage_hint,
            'currentPhase': phase,
            'activeFactionKey': (active_running or {}).get('factionKey'),
            'activeFactionLabel': (active_running or {}).get('factionLabel'),
            'activeFactionRole': (active_running or {}).get('factionRole'),
            'scanMode': 'detect_only',
        })
        if next_research_scan_at is not None:
            research['nextResearchScanAt'] = next_research_scan_at.isoformat(
                timespec='seconds',
            )
            research['allResearchDone'] = True
        elif clear_next_research_scan_at or incomplete_labels:
            research.pop('nextResearchScanAt', None)
            if incomplete_labels:
                research['allResearchDone'] = False
        if force_next_task_submit:
            research['forceNextTaskSubmit'] = True
        if task_submit_summary is not None:
            research = apply_task_submit_result_to_research(research, task_submit_summary)
        fill['research'] = research
        proalas['CollectionFill'] = fill
        deep_set(data, keys=['ProalasData'], value=proalas)
        write_file(path, data)

        txt_path = os.path.join('./config', f'{name}_research_incomplete.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(incomplete_labels))
            if incomplete_labels:
                f.write('\n')
        logger.info(
            'ResearchScan wrote incomplete=%s config=%s txt=%s',
            len(incomplete_labels),
            path,
            txt_path,
        )
        return txt_path

    def _maybe_run_task_submit(
        self,
        results: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, bool]:
        """
        对当前「研究进行中」船：到期或刚开研时跑「能交就交」。
        Returns:
            (summary_or_None, force_next_flag_if_started_but_not_run)
        """
        running = next(
            (r for r in results if isinstance(r, dict) and r.get('status') == 'running'),
            None,
        )
        if any(isinstance(r, dict) and r.get('status') == 'end' for r in results):
            logger.info('ResearchTaskSubmit skip: EndScienceBoat present — finish first')
            return None, False
        started = any(
            isinstance(r, dict) and r.get('startedByScan') for r in results
        )
        if not running:
            return None, False

        path = filepath_config(self._config_name())
        data = read_file(path)
        if not isinstance(data, dict):
            data = {}

        due = started or research_task_submit_due(data)
        if not due:
            logger.info('ResearchTaskSubmit skip: not due (72h / flags)')
            return None, False

        series = int(running.get('series') or 0)
        index = int(running.get('index') or 0)
        ship = str(running.get('ship') or '')
        logger.info(
            'ResearchTaskSubmit due series=%s index=%s ship=%r started=%s',
            series,
            index,
            ship,
            started,
        )
        if not self._shipyard_set_series(series, skip_first_screenshot=True):
            return {'error': 'series_select_failed', 'actions': []}, False
        self._wait_after_series(timeout=3.0)
        # 开研后槽位会重排：按「进行中」+船名校准，勿盲信扫到的旧 index
        new_index, new_ship, _st = self._relocate_ship_in_series(
            series,
            expect_ship=ship,
            want_status='running',
        )
        if new_index is None:
            logger.warning(
                'ResearchTaskSubmit relocate miss — fallback focus index=%s',
                index,
            )
            if not self._focus_ship_fixed(index):
                return {'error': 'focus_failed', 'actions': []}, False
        else:
            if new_index != index:
                logger.info(
                    'ResearchTaskSubmit slot recalibrated %s -> %s ship=%r',
                    index,
                    new_index,
                    new_ship or ship,
                )
            running['index'] = new_index
            if new_ship:
                running['ship'] = new_ship
            running['label'] = A.incomplete_label(
                series, running.get('ship') or '', index=new_index
            )

        summary = ResearchTaskSubmit(
            config=self.config,
            device=self.device,
        ).run_submit_pass()
        return summary, False

    def _click_start_research_confirm(self, timeout: float = 8.0) -> bool:
        """
        点「开始研究」后的确认：
        1) 原版 SHIPYARD_CONFIRM_DEV / FATE（购图/强化确认蓝钮）
        2) 通用弹窗 POPUP_CONFIRM（开始研究后更常见）
        """
        clicked = False
        fail = Timer(timeout).start()
        while 1:
            self.device.screenshot()
            if self.appear_then_click(SHIPYARD_CONFIRM_DEV, offset=(30, 30), interval=1.2):
                clicked = True
                continue
            if self.appear_then_click(SHIPYARD_CONFIRM_FATE, offset=(30, 30), interval=1.2):
                clicked = True
                continue
            if self.handle_popup_confirm('RESEARCH_START'):
                clicked = True
                continue
            # 已变成进行中则收工
            if self._is_research_running():
                return True
            if fail.reached():
                return clicked and self._is_research_running()

    def _start_research_on_ship(self, row: dict[str, Any]) -> dict[str, Any]:
        """对指定未完成船：点开始研究 → 确认 → 槽位校准 → 阵营同步。"""
        series = int(row.get('series') or 0)
        index = int(row.get('index') or 0)
        expect_ship = str(row.get('ship') or '')
        logger.hr(f'ResearchStart series={series} index={index}', level=2)

        if not self._shipyard_set_series(series, skip_first_screenshot=True):
            row = dict(row)
            row['startError'] = 'series_select_failed'
            return row
        self._wait_after_series(timeout=3.5)

        # 完成研究后同期也可能重排：有船名则先按名找「开始研究」槽
        if expect_ship:
            found_i, found_name, _found_st = self._relocate_ship_in_series(
                series,
                expect_ship=expect_ship,
                want_status='start',
            )
            if found_i is not None:
                if found_i != index:
                    logger.info(
                        'ResearchStart pre-start relocate %s -> %s ship=%r',
                        index,
                        found_i,
                        found_name or expect_ship,
                    )
                index = found_i
                if found_name:
                    expect_ship = found_name
            else:
                logger.warning(
                    'ResearchStart relocate by name miss — focus scan index=%s',
                    index,
                )
                if not self._focus_ship_fixed(index):
                    row = dict(row)
                    row['startError'] = 'focus_failed'
                    return row
        else:
            if not self._focus_ship_fixed(index):
                row = dict(row)
                row['startError'] = 'focus_failed'
                return row

        self.device.screenshot()
        if not self.match_template_color(
            A.START_SCIENCE_BOAT,
            offset=A.TEMPLATE_OFFSET,
            similarity=A.TEMPLATE_SIMILARITY,
        ):
            # 可能已被进行中，或误扫
            if self._is_research_running():
                logger.info('ResearchStart already running after focus')
            else:
                row = dict(row)
                row['startError'] = 'start_button_missing'
                return row
        else:
            logger.info('ResearchStart click StartScienceBoat')
            self.device.click(A.START_SCIENCE_BOAT)
            self.device.sleep(0.8)
            self._click_start_research_confirm()

        self.device.screenshot()
        row = dict(row)
        if not self._is_research_running():
            # 开研后船可能已跳槽：先校准再判失败
            new_i, new_name, new_st = self._relocate_ship_in_series(
                series,
                expect_ship=expect_ship,
                want_status='running',
            )
            if new_i is None or new_st != 'running':
                logger.warning('ResearchStart failed to reach running state')
                row['startError'] = 'not_running_after_confirm'
                row['status'] = new_st or self._detect_status()
                return row
            index = new_i
            if new_name:
                expect_ship = new_name
        else:
            # 当前已是进行中，仍须校准 index（开研后重排）
            new_i, new_name, _ = self._relocate_ship_in_series(
                series,
                expect_ship=expect_ship,
                want_status='running',
            )
            if new_i is not None:
                if new_i != index:
                    logger.info(
                        'ResearchStart post-start slot moved %s -> %s',
                        index,
                        new_i,
                    )
                index = new_i
                if new_name:
                    expect_ship = new_name

        ship = expect_ship or self._ocr_ship_name() or str(row.get('ship') or '')
        label = A.incomplete_label(series, ship, index=index)
        faction_info = self._sync_active_research_faction(
            series=series,
            index=index,
            ship=ship,
        )
        row.update({
            'ship': ship,
            'index': index,
            'label': label,
            'status': 'running',
            'completed': False,
            'startedByScan': True,
        })
        if faction_info:
            row['factionKey'] = faction_info.get('key')
            row['factionLabel'] = faction_info.get('labelZh')
            row['factionRole'] = faction_info.get('role')
            row['factionShort'] = faction_info.get('short')
        logger.info(
            'ResearchStart ok series=%s index=%s ship=%r faction=%s',
            series,
            index,
            ship,
            row.get('factionLabel'),
        )
        return row

    def _click_end_research(self) -> bool:
        """
        点「完成研究」后会出现不可交互结算层；
        在完成研究按钮位置连点 3 次（间隔 1s）回到可判断界面。
        """
        logger.info(
            'ResearchEnd click EndScienceBoat x%s interval=%ss',
            A.END_SCIENCE_BOAT_CLICKS,
            A.END_SCIENCE_BOAT_CLICK_INTERVAL,
        )
        for i in range(A.END_SCIENCE_BOAT_CLICKS):
            self.device.click(A.END_SCIENCE_BOAT)
            self.device.sleep(A.END_SCIENCE_BOAT_CLICK_INTERVAL)
            logger.info('ResearchEnd click step=%s/%s', i + 1, A.END_SCIENCE_BOAT_CLICKS)
        self.device.screenshot()
        # 成功：橙钮消失（回到船坞判断界面，可能仍在该船详情）
        if self._is_research_end():
            logger.warning('ResearchEnd EndScienceBoat still visible after clicks')
            return False
        return True

    def _finish_end_research_on_ship(self, row: dict[str, Any]) -> dict[str, Any]:
        """聚焦并点完成研究；成功则标 completed。"""
        series = int(row.get('series') or 0)
        index = int(row.get('index') or 0)
        logger.hr(f'ResearchEnd series={series} index={index}', level=2)

        if not self._shipyard_set_series(series, skip_first_screenshot=True):
            out = dict(row)
            out['endError'] = 'series_select_failed'
            return out
        self._wait_after_series(timeout=3.0)
        if not self._focus_ship_fixed(index):
            out = dict(row)
            out['endError'] = 'focus_failed'
            return out

        self.device.screenshot()
        if not self._is_research_end():
            status = self._detect_status()
            out = dict(row)
            out['status'] = status
            if status == 'completed':
                out['completed'] = True
                out['label'] = ''
                out['endedByScan'] = True
            else:
                out['endError'] = 'end_button_missing'
            return out

        if not self._click_end_research():
            out = dict(row)
            out['endError'] = 'end_click_failed'
            out['status'] = self._detect_status()
            return out

        ship = self._ocr_ship_name() or str(row.get('ship') or '')
        out = dict(row)
        out.update({
            'ship': ship,
            'label': '',
            'status': 'completed',
            'completed': True,
            'endedByScan': True,
        })
        logger.info(
            'ResearchEnd ok series=%s index=%s ship=%r',
            series,
            index,
            ship,
        )
        return out

    def _maybe_finish_end_and_advance(
        self,
        results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        """
        若有 status=end：点完成研究。
        - 点之前未完成数量（含本船）== 1 → 推迟下次扫描 180 天
        - 否则开下一艘最大期未完成（start）并换队
        Returns:
            (updated_results, next_research_scan_at_or_None)
        """
        end_rows = [
            r for r in results
            if isinstance(r, dict) and r.get('status') == 'end'
        ]
        if not end_rows:
            return results, None

        # 通常同时只有一艘在科研末尾；取期数/槽最大的那个
        target = max(
            end_rows,
            key=lambda r: (int(r.get('series') or 0), int(r.get('index') or 0)),
        )
        incomplete_before = [
            r for r in results
            if isinstance(r, dict) and r.get('completed') is False
        ]
        incomplete_count = len(incomplete_before)
        logger.info(
            'ResearchEnd pick series=%s index=%s incomplete_count=%s (from scan results)',
            target.get('series'),
            target.get('index'),
            incomplete_count,
        )

        finished = self._finish_end_research_on_ship(target)
        out: list[dict[str, Any]] = []
        for r in results:
            if (
                isinstance(r, dict)
                and r.get('series') == target.get('series')
                and r.get('index') == target.get('index')
            ):
                out.append(finished)
            else:
                out.append(r)

        if not finished.get('endedByScan'):
            return out, None

        if incomplete_count <= 1:
            pause_until = datetime.now() + timedelta(days=A.RESEARCH_ALL_DONE_PAUSE_DAYS)
            logger.info(
                'ResearchEnd last incomplete finished — pause scan until %s',
                pause_until.isoformat(timespec='seconds'),
            )
            return out, pause_until

        # 还有其它未完成：开最大期 start 船
        logger.info('ResearchEnd more incomplete remain — start next research')
        out = self._maybe_start_highest_incomplete(out)
        return out, None

    def _maybe_start_highest_incomplete(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        有未完成但没有任何「研究进行中 / 待完成研究」时：
        选期数最大的未完成船（同最大期则 index 最大）→ 开始研究 → 阵营同步。
        """
        blocking = [
            r for r in results
            if isinstance(r, dict) and r.get('status') in ('running', 'end')
        ]
        if blocking:
            logger.info(
                'ResearchStart skip: have running/end research status=%s',
                [r.get('status') for r in blocking],
            )
            return results

        candidates = [
            r for r in results
            if isinstance(r, dict) and r.get('status') == 'start'
        ]
        if not candidates:
            logger.info('ResearchStart skip: no startable incomplete ships')
            return results

        target = max(
            candidates,
            key=lambda r: (int(r.get('series') or 0), int(r.get('index') or 0)),
        )
        logger.info(
            'ResearchStart pick highest incomplete series=%s index=%s label=%s',
            target.get('series'),
            target.get('index'),
            target.get('label'),
        )
        updated = self._start_research_on_ship(target)
        out: list[dict[str, Any]] = []
        for r in results:
            if (
                isinstance(r, dict)
                and r.get('series') == target.get('series')
                and r.get('index') == target.get('index')
            ):
                out.append(updated)
            else:
                out.append(r)
        return out

    def _rebuild_incomplete_labels(self, results: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        for r in results:
            if not isinstance(r, dict) or r.get('completed') is not False:
                continue
            label = str(r.get('label') or '').strip()
            if label and label not in labels:
                labels.append(label)
        return labels

    def scan_all(self) -> list[str]:
        """
        Pages:
            in: Any
            out: page_shipyard

        规则：1–2 期最多 6 槽；3 期起固定 5 槽，底部位置沿用，不因单艘失败而跳过整期。
        扫完：先处理「完成研究」→ 若还有未完成则开最大期；无进行中则开研；
        再对进行中船做任务能交就交（有 End 时跳过任务提交）。
        """
        logger.hr('ProalasResearchScan', level=1)
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        self.ui_goto(page_shipyard)

        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for series in range(1, A.SERIES_COUNT + 1):
            logger.hr(f'ResearchScan series {series}', level=2)
            if not self._shipyard_set_series(series, skip_first_screenshot=True):
                msg = f'series_{series}_select_failed'
                logger.warning('ResearchScan %s', msg)
                errors.append(msg)
                continue

            self.device.screenshot()
            # 8 期等待稍长；无论 nav 色是否就绪都继续按固定槽点
            wait_s = 5.0 if series >= 8 else 3.5
            self._wait_after_series(timeout=wait_s)

            max_index = A.max_ship_index(series)
            logger.info(
                'ResearchScan series=%s scan fixed slots 1..%s',
                series,
                max_index,
            )

            for index in range(1, max_index + 1):
                ok = self._focus_ship_fixed(index, settle=1.4)
                if not ok:
                    msg = f'series_{series}_index_{index}_focus_failed'
                    logger.warning('ResearchScan %s — continue next slot', msg)
                    errors.append(msg)
                    results.append({
                        'series': series,
                        'index': index,
                        'ship': '',
                        'label': '',
                        'status': 'error',
                        'completed': None,
                        'error': msg,
                    })
                    continue

                if not self._shipyard_in_ui():
                    msg = f'series_{series}_index_{index}_not_in_ui'
                    logger.warning('ResearchScan %s — continue next slot', msg)
                    errors.append(msg)
                    results.append({
                        'series': series,
                        'index': index,
                        'ship': '',
                        'label': '',
                        'status': 'error',
                        'completed': None,
                        'error': msg,
                    })
                    continue

                results.append(self._scan_ship(series, index))

        # 1) 完成研究 → 最后一艘则推迟半年，否则开下一艘
        results, pause_until = self._maybe_finish_end_and_advance(results)
        # 2) 无进行中/待完成时开最大期未完成
        results = self._maybe_start_highest_incomplete(results)
        incomplete_labels = self._rebuild_incomplete_labels(results)

        # 3) 任务能交就交（有 End 时内部会 skip）
        task_summary, _ = self._maybe_run_task_submit(results)
        force_next = any(
            isinstance(r, dict) and r.get('startedByScan') for r in results
        ) and task_summary is None

        self._write_results(
            results=results,
            incomplete_labels=incomplete_labels,
            errors=errors,
            task_submit_summary=task_summary,
            force_next_task_submit=force_next,
            next_research_scan_at=pause_until,
            clear_next_research_scan_at=bool(incomplete_labels),
        )
        logger.info(
            'ResearchScan done incomplete=%s errors=%s labels=%s task_submit=%s pause=%s',
            len(incomplete_labels),
            len(errors),
            incomplete_labels,
            (task_summary or {}).get('submittedCount'),
            pause_until.isoformat(timespec='seconds') if pause_until else None,
        )
        return incomplete_labels

    def run(self, *, skip_gate: bool = False, skip_task_delay: bool = False) -> list[str]:
        if not skip_gate and gate_task_or_skip(self, 'ProalasCollectionFill'):
            return []
        return self.scan_all()
