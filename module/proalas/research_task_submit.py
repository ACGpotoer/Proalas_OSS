# -*- coding: utf-8 -*-
"""
科研任务「能交就交」（阶段图标优先）：

- 仅 running 船有底栏 8 格：RD=已完成跳过 / RI=未解锁跳过 / RY=打开并交
- 详情页：SubmitNone 或 蓝钮 Submit；回列表只点灰钮 SubmitNone
- 蓝钮点击会真正提交，仍停在详情，再点灰钮回全量列表
- 技术测试 1/4：打开后 OCR 标题阵营 → 写 LevelTeamFaction
- 前 4 任务上滑置顶，后 4 下滑到底
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.CollectionFill import assets as A
from module.base.timer import Timer
from module.logger import logger
from module.proalas.research_faction import (
    apply_level_team_faction,
    faction_from_task_title,
)
from module.proalas.research_stage_match import scan_research_stages
from module.proalas.research_task_ocr import find_keyword_click, scan_task_titles
from module.proalas.research_task_policy import mark_task_submit_ran
from module.ui.ui import UI


class ResearchTaskSubmit(UI):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _tap(self, xy: tuple[int, int], *, delay: float = 0.6) -> None:
        self.device.click_adb(int(xy[0]), int(xy[1]))
        self.device.sleep(delay)

    def _swipe_list_to_top(self) -> None:
        logger.info('ResearchTask swipe to top')
        self.device.swipe(
            A.RESEARCH_TASK_SWIPE_TOP,
            A.RESEARCH_TASK_SWIPE_BOTTOM,
            duration=A.RESEARCH_TASK_SWIPE_DURATION,
            name='RESEARCH_TASK_TOP',
            distance_check=False,
        )
        self.device.sleep(0.7)

    def _swipe_list_to_bottom(self) -> None:
        logger.info('ResearchTask swipe to bottom')
        self.device.swipe(
            A.RESEARCH_TASK_SWIPE_BOTTOM,
            A.RESEARCH_TASK_SWIPE_TOP,
            duration=A.RESEARCH_TASK_SWIPE_DURATION,
            name='RESEARCH_TASK_BOTTOM',
            distance_check=False,
        )
        self.device.sleep(0.7)

    def _match_submit_blue(self) -> bool:
        return self.match_template_color(
            A.SUBMIT_RESEARCH_TASK,
            offset=A.SUBMIT_TEMPLATE_OFFSET,
            similarity=A.SUBMIT_TEMPLATE_SIMILARITY,
        )

    def _match_submit_none(self) -> bool:
        return self.match_template_color(
            A.SUBMIT_NONE,
            offset=A.SUBMIT_TEMPLATE_OFFSET,
            similarity=A.SUBMIT_TEMPLATE_SIMILARITY,
        )

    def _on_detail_panel(self) -> bool:
        """详情/提交检测页：灰钮或蓝钮任一出现。"""
        return self._match_submit_none() or self._match_submit_blue()

    def _click_submit_none(self) -> None:
        """灰钮：回全量列表（或提交后的二次确认位）。"""
        logger.info('ResearchTask click SubmitNone → list')
        self.device.click(A.SUBMIT_NONE)
        self.device.sleep(0.8)

    def _ensure_list_panel(self) -> bool:
        """
        回到全量任务列表。
        仅点灰钮；若只有蓝钮则先提交再点灰钮（能交就交场景下可接受）。
        """
        self.device.screenshot()
        if not self._on_detail_panel():
            return True
        if self._match_submit_blue():
            logger.info('ResearchTask detail has blue submit — submit then SubmitNone')
            self.device.click(A.SUBMIT_RESEARCH_TASK)
            self.device.sleep(1.0)
            fail = Timer(4.0).start()
            while 1:
                self.device.screenshot()
                if self._match_submit_none():
                    break
                if fail.reached():
                    logger.warning('ResearchTask wait SubmitNone after blue timeout')
                    break
                self.device.sleep(0.4)
        if self._match_submit_none():
            self._click_submit_none()
        self.device.screenshot()
        if self._on_detail_panel():
            logger.warning('ResearchTask still on detail after ensure_list')
            return False
        return True

    def _prepare_list_for_slot(self, slot: int) -> None:
        if slot <= 4:
            self._swipe_list_to_top()
        else:
            self._swipe_list_to_bottom()

    def _open_task_slot(self, slot: int, keyword: str) -> str:
        """
        打开任务。Returns:
            OCR 到的标题文本（可能为空）
        """
        self._prepare_list_for_slot(slot)
        self.device.screenshot()
        # 同关键字多条时：顶部取第一条，底部也取当前屏第一条（测2在下滑后靠前）
        title = ''
        for row in scan_task_titles(self.device.image, row_count=10):
            if row.get('keyword') == keyword:
                title = str(row.get('text') or '')
                break
        pt = find_keyword_click(self.device.image, keyword, row_count=10)
        if not pt:
            logger.info('ResearchTask open miss slot=%s kw=%s', slot, keyword)
            return ''
        logger.info('ResearchTask open slot=%s kw=%s at %s title=%r', slot, keyword, pt, title)
        self._tap(pt, delay=0.9)
        self.device.screenshot()
        return title

    def _apply_faction_from_title(self, title: str, *, slot: int) -> dict | None:
        info = faction_from_task_title(title)
        if not info:
            # 详情页再 OCR 一次右侧
            from module.proalas.research_task_ocr import scan_task_titles as _scan
            self.device.screenshot()
            for row in _scan(self.device.image, row_count=8):
                info = faction_from_task_title(str(row.get('text') or ''))
                if info:
                    break
        if not info:
            logger.warning('ResearchTask faction miss slot=%s title=%r', slot, title)
            return None
        apply_level_team_faction(self._config_name(), str(info['key']))
        logger.info(
            'ResearchTask faction slot=%s %s/%s %s',
            slot,
            info.get('short'),
            info.get('role'),
            info.get('labelZh'),
        )
        return info

    def _submit_opened_ready_task(self) -> str:
        """
        已打开 RY 任务详情。
        Returns:
            'submitted' | 'skipped' | 'error'
        """
        self.device.screenshot()
        # 等待详情控件
        appear = Timer(3.0).start()
        while 1:
            if self._on_detail_panel():
                break
            if appear.reached():
                logger.warning('ResearchTask detail controls not found')
                return 'error'
            self.device.sleep(0.35)
            self.device.screenshot()

        if self._match_submit_blue():
            logger.info('ResearchTask blue Submit — click')
            self.device.click(A.SUBMIT_RESEARCH_TASK)
            self.device.sleep(1.0)
            wait = Timer(5.0).start()
            while 1:
                self.device.screenshot()
                if self._match_submit_none() and not self._match_submit_blue():
                    break
                if wait.reached():
                    logger.warning('ResearchTask after submit: SubmitNone not stable')
                    break
                self.device.sleep(0.4)
            if self._match_submit_none():
                self._click_submit_none()
            return 'submitted'

        if self._match_submit_none():
            logger.info('ResearchTask grey SubmitNone only — not submittable, back to list')
            self._click_submit_none()
            return 'skipped'

        return 'error'

    def run_submit_pass(self) -> dict[str, Any]:
        """假定已在 running 科研船详情页。"""
        logger.hr('ResearchTaskSubmit', level=2)
        summary: dict[str, Any] = {
            'at': datetime.now().isoformat(timespec='seconds'),
            'actions': [],
            'submittedTechTest1': False,
            'stages': [],
        }

        self.device.screenshot()
        stages = scan_research_stages(self.device.image)
        summary['stages'] = [
            {'index': s['index'], 'status': s['status'], 'keyword': s['keyword'], 'score': s['score']}
            for s in stages
        ]
        ready = [s for s in stages if s['status'] == 'ready']
        if not ready:
            # 无 RY：可能不在 running 页或全完成
            if all(s['status'] == 'unknown' for s in stages):
                summary['error'] = 'stages_unknown'
                logger.warning('ResearchTask stages all unknown — skip submit pass')
            else:
                logger.info('ResearchTask no RY slots — nothing to submit')
            summary['submittedCount'] = 0
            return summary

        if not self._ensure_list_panel():
            summary['error'] = 'cannot_reach_list'
            summary['submittedCount'] = 0
            return summary

        submitted_tech1 = False
        for stage in stages:
            slot = int(stage['index'])
            status = stage['status']
            keyword = str(stage['keyword'])
            action: dict[str, Any] = {
                'slot': slot,
                'keyword': keyword,
                'stage': status,
            }
            if status == 'done':
                action['result'] = 'skip_done'
                summary['actions'].append(action)
                continue
            if status == 'locked':
                action['result'] = 'skip_locked'
                summary['actions'].append(action)
                continue
            if status != 'ready':
                action['result'] = 'skip_unknown'
                summary['actions'].append(action)
                continue

            if not self._ensure_list_panel():
                action['result'] = 'no_list'
                summary['actions'].append(action)
                continue

            title = self._open_task_slot(slot, keyword)
            if slot in A.RESEARCH_STAGE_TECH_TEST_SLOTS:
                faction = self._apply_faction_from_title(title, slot=slot)
                if faction:
                    action['factionKey'] = faction.get('key')
                    action['factionLabel'] = faction.get('labelZh')

            result = self._submit_opened_ready_task()
            action['result'] = result
            summary['actions'].append(action)
            if result == 'submitted' and slot == 1:
                submitted_tech1 = True
            logger.info('ResearchTask slot=%s %s -> %s', slot, keyword, result)

        summary['submittedTechTest1'] = submitted_tech1
        summary['submittedCount'] = sum(
            1 for a in summary['actions'] if a.get('result') == 'submitted'
        )
        logger.info(
            'ResearchTaskSubmit done submitted=%s tech1=%s actions=%s',
            summary['submittedCount'],
            summary['submittedTechTest1'],
            summary['actions'],
        )
        return summary


def apply_task_submit_result_to_research(
    research: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    out = mark_task_submit_ran(
        research,
        submitted_tech_test_1=bool(summary.get('submittedTechTest1')),
    )
    tech_subs = [
        a for a in (summary.get('actions') or [])
        if a.get('keyword') == '技术测试' and a.get('result') == 'submitted'
    ]
    if summary.get('submittedTechTest1') and len(tech_subs) == 1:
        out['techTest1SubmittedAwaitTech2'] = True
    if len(tech_subs) >= 2:
        out['techTest1SubmittedAwaitTech2'] = False
    out['lastTaskSubmitSummary'] = {
        'submittedCount': summary.get('submittedCount'),
        'actions': summary.get('actions'),
        'stages': summary.get('stages'),
        'error': summary.get('error'),
    }
    out['forceNextTaskSubmit'] = False
    return out
