# -*- coding: utf-8 -*-
"""
ProAlas 自动 UP 抽卡补齐：复用 RewardGacha 执行，门禁见 auto_gacha_policy。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.utils import filepath_config, read_file, write_file
from module.gacha.gacha_reward import OCR_BUILD_CUBE_COUNT, RewardGacha
from module.logger import logger
from module.proalas.auto_gacha_policy import (
    EVENT_CUBE_COST,
    evaluate_auto_gacha,
    server_day_key,
)
from module.proalas.feature_gate import gate_task_or_skip
from module.proalas.gacha_up_check import ProalasGachaCheck


class ProalasAutoGacha(RewardGacha):
    def _config_name(self) -> str:
        return str(getattr(self.config, 'config_name', '') or 'alas')

    def _read_cubes_ocr(self) -> int | None:
        try:
            self.ui_goto_gacha()
            self.device.screenshot()
            return int(OCR_BUILD_CUBE_COUNT.ocr(self.device.image))
        except Exception as e:
            logger.warning('AutoGacha cube OCR failed: %s', e)
            return None

    def _snapshot_gacha_config(self) -> dict[str, Any]:
        return {
            'Gacha_Pool': getattr(self.config, 'Gacha_Pool', 'light'),
            'Gacha_Amount': getattr(self.config, 'Gacha_Amount', 1),
            'Gacha_UseTicket': getattr(self.config, 'Gacha_UseTicket', True),
            'Gacha_UseDrill': getattr(self.config, 'Gacha_UseDrill', False),
        }

    def _restore_gacha_config(self, saved: dict[str, Any]) -> None:
        for key, value in saved.items():
            setattr(self.config, key, value)

    def _execute_event_pull(self, pull_count: int) -> bool:
        saved = self._snapshot_gacha_config()
        self.config.Gacha_Pool = 'event'
        self.config.Gacha_Amount = pull_count
        self.config.Gacha_UseTicket = True
        self.config.Gacha_UseDrill = True
        try:
            return bool(self.gacha_run())
        finally:
            self._restore_gacha_config(saved)

    def _write_gacha_auto(self, payload: dict[str, Any]) -> None:
        name = self._config_name()
        path = filepath_config(name)
        data = read_file(path)
        if not isinstance(data, dict):
            logger.warning('AutoGacha config missing %s', path)
            return
        proalas = dict(deep_get(data, ['ProalasData'], {}) or {})
        gacha_auto = dict(proalas.get('GachaAuto') or {})
        gacha_auto.update(payload)
        proalas['GachaAuto'] = gacha_auto
        deep_set(data, keys=['ProalasData'], value=proalas)
        write_file(path, data)

    def _record_skip(self, reason: str, *, cubes: int | None = None) -> None:
        day = server_day_key()
        gacha_auto = deep_get(self.config.data, ['ProalasData', 'GachaAuto'], {}) or {}
        today_pulls = 0
        if isinstance(gacha_auto, dict) and str(gacha_auto.get('date') or '') == day:
            try:
                today_pulls = max(0, int(gacha_auto.get('todayPulls', 0)))
            except (TypeError, ValueError):
                today_pulls = 0
        self._write_gacha_auto({
            'date': day,
            'todayPulls': today_pulls,
            'lastState': 'skipped',
            'lastReason': reason,
            'lastRunAt': datetime.now().isoformat(timespec='seconds'),
            'cubesLast': cubes,
        })
        logger.info('AutoGacha skipped reason=%s cubes=%s', reason, cubes)

    def _verify_missing_ships(self, missing: list[str]) -> None:
        if not missing:
            return
        ProalasGachaCheck(config=self.config, device=self.device).run(
            skip_gate=True,
            skip_task_delay=True,
            ships_only=missing,
        )
        self.config.load()

    def run(
        self,
        *,
        skip_gate: bool = False,
        skip_task_delay: bool = False,
        event_day: bool | None = None,
    ) -> None:
        if not skip_gate and gate_task_or_skip(self, 'ProalasCollectionFill'):
            return
        logger.hr('ProalasAutoGacha', level=1)

        self.config.load()
        cubes_before = self._read_cubes_ocr()
        gate = evaluate_auto_gacha(
            self.config.data,
            cubes=cubes_before,
            event_day=event_day,
        )
        if not gate.ok:
            self._record_skip(gate.reason, cubes=cubes_before)
            if not skip_task_delay:
                self.config.task_delay(server_update=True)
            return

        pull_count = gate.pull_count
        logger.info(
            'AutoGacha pull_count=%s cubes_before=%s event_day=%s',
            pull_count,
            cubes_before,
            event_day,
        )

        day = server_day_key()
        gacha_auto = deep_get(self.config.data, ['ProalasData', 'GachaAuto'], {}) or {}
        today_pulls = 0
        if isinstance(gacha_auto, dict) and str(gacha_auto.get('date') or '') == day:
            try:
                today_pulls = max(0, int(gacha_auto.get('todayPulls', 0)))
            except (TypeError, ValueError):
                today_pulls = 0

        missing = [
            str(x).strip()
            for x in deep_get(self.config.data, ['ProalasData', 'GachaUp', 'missing'], [])
            if str(x).strip()
        ]

        pulled = False
        try:
            pulled = self._execute_event_pull(pull_count)
        except Exception as e:
            logger.warning('AutoGacha execute failed: %s', e)
            self._write_gacha_auto({
                'date': day,
                'todayPulls': today_pulls,
                'lastState': 'error',
                'lastReason': str(e),
                'lastRunAt': datetime.now().isoformat(timespec='seconds'),
                'cubesBefore': cubes_before,
                'plannedPulls': pull_count,
            })
            if not skip_task_delay:
                self.config.task_delay(success=False)
            return

        cubes_after = self._read_cubes_ocr()
        new_today = today_pulls + (pull_count if pulled else 0)

        if pulled and missing:
            self._verify_missing_ships(missing)

        self._write_gacha_auto({
            'date': day,
            'todayPulls': new_today,
            'lastState': 'done' if pulled else 'no_submit',
            'lastReason': 'ok' if pulled else 'gacha_run_false',
            'lastRunAt': datetime.now().isoformat(timespec='seconds'),
            'cubesBefore': cubes_before,
            'cubesAfter': cubes_after,
            'plannedPulls': pull_count,
            'cubeCostEstimate': pull_count * EVENT_CUBE_COST,
        })
        logger.info(
            'AutoGacha done pulled=%s today_pulls=%s cubes %s→%s',
            pulled,
            new_today,
            cubes_before,
            cubes_after,
        )
        if not skip_task_delay:
            self.config.task_delay(server_update=True)


def maybe_run_auto_gacha_after_check(config, device, *, event_day: bool) -> None:
    """定时计划 bundle：UP 检测通过后可选执行自动抽卡（建造补齐）。"""
    from module.proalas.collection_fill_policy import build_fill_enabled, collection_fill_enabled

    config.load()
    config.bind('ProalasCollectionFill')
    data = config.data if hasattr(config, 'data') else {}
    if not collection_fill_enabled(data):
        logger.info('AutoGacha bundle skip: CollectionFill.Enable=false')
        return
    if not build_fill_enabled(data):
        logger.info('AutoGacha bundle skip: BuildEnable=false')
        return
    if not bool(getattr(config, 'ProalasCollectionFill_AutoGachaEnable', False)):
        logger.info('AutoGacha bundle skip: AutoGachaEnable=false')
        return
    ProalasAutoGacha(config=config, device=device).run(
        skip_gate=True,
        skip_task_delay=True,
        event_day=event_day,
    )
