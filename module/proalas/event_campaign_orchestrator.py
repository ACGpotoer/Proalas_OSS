# -*- coding: utf-8 -*-
"""
活动日编排器（T-HT 模板）。

在日历物化之后、AI 规划之前，为 Event / Event2 写入推图期默认配置。
章节名 t* = T 线，ht* = HT 线；不写 Campaign.Mode。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.event_tht_config import (
    MAP_ACH_FARM,
    MAP_ACH_PUSH,
    THT_EVENT2_TASK,
    THT_EVENT_TASK,
    THT_HARD_STAGES,
    THT_NORMAL_STAGES,
    apply_tht_to_config_data,
)

@dataclass
class OrchestrateResult:
    device_id: str
    date: str
    event_day: bool = False
    phase: str = ''
    skipped: bool = False
    reason: str = ''
    applied: int = 0
    details: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.skipped and not self.reason.startswith('error:')


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def is_event_day_blue(blue: dict[str, Any] | None) -> bool:
    """蓝区是否为活动日。空蓝区 / mode=none → 否（勿因 FormatFix 残留判为活动日）。"""
    if not isinstance(blue, dict) or not blue:
        return False
    mode = str(blue.get('mode') or '').strip().lower()
    if mode == 'none':
        return False
    if mode == 'event':
        return True
    fmt = str(blue.get('event_format') or '').strip().upper()
    if fmt and fmt not in ('NONE',):
        return True
    campaigns = blue.get('campaign_events') or {}
    if isinstance(campaigns, dict):
        for val in campaigns.values():
            text = str(val or '').strip()
            if text and text != 'campaign_main':
                return True
    sched = blue.get('scheduler_enable') or {}
    if not isinstance(sched, dict):
        return False
    # 不含 ProalasEventFormatFix：检测任务开关不能单独定义「活动日」
    for key in (THT_EVENT_TASK, THT_EVENT2_TASK, 'EventA', 'EventB', 'Coalition', 'Raid', 'RaidDaily'):
        if sched.get(key):
            return True
    return False


def _event_format_template(config_data: dict[str, Any]) -> str:
    tpl = deep_get(config_data, ['ProalasData', 'EventFormat', 'template'], '')
    if not tpl:
        tpl = deep_get(config_data, ['ProalasEventFormatFix', 'ProalasEventFormatFix', 'Template'], '')
    return str(tpl or '').strip().upper()


def _t_line_cleared(config_data: dict[str, Any]) -> bool:
    return bool(deep_get(config_data, ['ProalasEventFormatFix', 'ProalasEventFormatFix', 'AllCleared'], False))


def _resolve_tht_phases(config_data: dict[str, Any]) -> tuple[str, str, str, str]:
    """返回 event_stage, event2_stage, map_achievement, phase_name。"""
    if _t_line_cleared(config_data):
        farm = THT_HARD_STAGES[-1]
        return farm, farm, MAP_ACH_FARM, 'farm_t_cleared'

    event_name = str(deep_get(config_data, ['Event', 'Campaign', 'Name'], '') or '').strip().lower()
    event2_name = str(deep_get(config_data, ['Event2', 'Campaign', 'Name'], '') or '').strip().lower()

    if event_name and event2_name:
        if event_name != THT_NORMAL_STAGES[0] or event2_name != THT_HARD_STAGES[0]:
            ach = str(
                deep_get(config_data, ['Event', 'StopCondition', 'MapAchievement'], MAP_ACH_PUSH)
                or MAP_ACH_PUSH
            )
            return event_name, event2_name, ach, 'push_in_progress'

    return (
        THT_NORMAL_STAGES[0],
        THT_HARD_STAGES[0],
        MAP_ACH_PUSH,
        'push_normal',
    )


def orchestrate_event_campaign(
    device_id: str,
    *,
    blue: dict[str, Any] | None = None,
    on_date: str | None = None,
    config_data: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> OrchestrateResult:
    device_id = str(device_id or '').strip()
    date_str = str(on_date or _today_str())
    result = OrchestrateResult(device_id=device_id, date=date_str, dry_run=dry_run)

    if blue is None:
        from module.proalas.plan_quadrant_view import get_blue_payload
        import module.config.server as server_mod

        blue = get_blue_payload(device_id, date_str, server=getattr(server_mod, 'server', 'cn'))

    if not is_event_day_blue(blue):
        result.skipped = True
        result.reason = 'not_event_day'
        return result

    result.event_day = True

    if config_data is None:
        config_data = read_file(filepath_config(device_id))
    if not isinstance(config_data, dict):
        result.skipped = True
        result.reason = 'error:config_missing'
        return result

    template = _event_format_template(config_data)
    if template == 'COALITION':
        # 共斗：只关主线，不做 T-HT 推图写入
        patches = []
        for main_task in ('Main', 'Main2'):
            sched = deep_get(config_data, [main_task, 'Scheduler', 'Enable'], None)
            if sched is not False:
                deep_set(config_data, keys=[main_task, 'Scheduler', 'Enable'], value=False)
                patches.append(f'{main_task}.Scheduler.Enable=false')
        result.applied = len(patches)
        result.details = patches
        result.phase = 'coalition'
        if dry_run:
            return result
        if patches:
            write_file(filepath_config(device_id), config_data)
        logger.info('EventOrchestrator coalition day device=%s applied=%s', device_id, result.applied)
        return result

    if template and template != 'T-HT':
        result.skipped = True
        result.reason = f'unsupported_template:{template}'
        return result

    event_stage, event2_stage, map_ach, phase = _resolve_tht_phases(config_data)
    patches = apply_tht_to_config_data(
        config_data,
        event_stage=event_stage,
        event2_stage=event2_stage,
        map_achievement=map_ach,
    )

    for main_task in ('Main', 'Main2'):
        sched = deep_get(config_data, [main_task, 'Scheduler', 'Enable'], None)
        if sched is not False:
            deep_set(config_data, keys=[main_task, 'Scheduler', 'Enable'], value=False)
            patches.append(f'{main_task}.Scheduler.Enable=false')

    state = deep_get(config_data, ['ProalasData', 'EventCampaignState'], {}) or {}
    if not isinstance(state, dict):
        state = {}
    state.update({
        'date': date_str,
        'template': 'T-HT',
        'phase': phase,
        'easyTask': THT_EVENT_TASK,
        'hardTask': THT_EVENT2_TASK,
        'orchestratedAt': datetime.now().isoformat(timespec='seconds'),
    })
    proalas = deep_get(config_data, ['ProalasData'], {}) or {}
    if not isinstance(proalas, dict):
        proalas = {}
    proalas['EventCampaignState'] = state
    deep_set(config_data, keys=['ProalasData'], value=proalas)

    result.applied = len(patches)
    result.details = patches
    result.phase = phase

    if dry_run:
        logger.info('EventOrchestrator dry-run device=%s phase=%s', device_id, phase)
        return result

    write_file(filepath_config(device_id), config_data)
    logger.info('EventOrchestrator device=%s date=%s phase=%s applied=%s', device_id, date_str, phase, result.applied)
    return result
