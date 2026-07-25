# -*- coding: utf-8 -*-
"""定时计划主任务：统一开关 + 串行执行活动同步 / UP 抽卡检测。"""
from __future__ import annotations

from typing import Any

from module.config.deep import deep_set
from module.logger import logger

# 仅 ProalasTimerPlan 进调度队列；子功能由主任务 run() 串行调用
BUNDLE_CHILD_TASKS = (
    'ProalasActivitySync',
    'ProalasGachaCheck',
    'ProalasBoatMessage',
)


def normalize_timer_plan_bundle(data: dict[str, Any]) -> None:
    """子任务永不单独进队（避免队列里只剩「活动同步」）；仅 ProalasTimerPlan 主开关有效。"""
    if not isinstance(data, dict):
        return
    for task in BUNDLE_CHILD_TASKS:
        body = data.get(task)
        if not isinstance(body, dict):
            continue
        sched = body.get('Scheduler')
        if not isinstance(sched, dict):
            continue
        sched['Enable'] = False


def run_timer_plan_bundle(config, device) -> None:
    """主任务一次跑完：云端拉取+物化 → UP 检测 → TimeTable 刷新。"""
    from module.proalas.activity_materializer import materialize_activity
    from module.proalas.activity_sync import ProalasActivitySync
    from module.proalas.gacha_up_check import ProalasGachaCheck
    from module.proalas.time_table import update_device_timetable

    device_id = str(getattr(config, 'config_name', '') or 'alas')

    logger.info('TimerPlan bundle: activity sync (pull + materialize)')
    sync = ProalasActivitySync(config=config, device=device)
    sync._pull_sync_gateway()
    allow_manifest = bool(getattr(config, 'ProalasActivitySync_AllowManifestFallback', True))
    mat = materialize_activity(device_id, allow_manifest_fallback=allow_manifest)
    if mat.errors:
        logger.error('TimerPlan materialize errors=%s', mat.errors)
    else:
        logger.info('TimerPlan materialize applied=%s date=%s', mat.applied, mat.date)

    from module.proalas.event_campaign_orchestrator import is_event_day_blue, orchestrate_event_campaign

    event_day = is_event_day_blue(mat.blue)
    if event_day:
        orch = orchestrate_event_campaign(device_id, blue=mat.blue)
        if orch.event_day:
            logger.info(
                'TimerPlan event orchestrate device=%s phase=%s applied=%s',
                device_id,
                orch.phase or '-',
                orch.applied,
            )
        elif orch.reason and not orch.skipped:
            logger.warning('TimerPlan event orchestrate device=%s reason=%s', device_id, orch.reason)
    else:
        logger.info('TimerPlan skip event orchestrate — not_event_day mode=%s', (mat.blue or {}).get('mode'))

    config.load()
    config.bind('ProalasTimerPlan')

    if event_day:
        logger.info('TimerPlan bundle: gacha check (event day)')
        ProalasGachaCheck(config=config, device=device).run(skip_gate=True, skip_task_delay=True)
        config.load()
        config.bind('ProalasTimerPlan')
        from module.proalas.auto_gacha import maybe_run_auto_gacha_after_check

        maybe_run_auto_gacha_after_check(config, device, event_day=True)
    else:
        logger.info('TimerPlan skip gacha check — not_event_day (UP 池与活动共生)')

    config.load()
    config.bind('ProalasTimerPlan')
    from module.proalas.research_scan_schedule import maybe_run_research_scan_if_due

    maybe_run_research_scan_if_due(config, device)

    config.load()
    config.bind('ProalasTimerPlan')

    logger.info('TimerPlan bundle: resource collector (S3 before AI)')
    from module.proalas_collector.collector import ProalasCollector

    ProalasCollector(config=config, device=device).run(skip_task_delay=True)

    config.load()
    config.bind('ProalasTimerPlan')

    raw_exclude = getattr(config, 'ProalasTimerPlan_ExtraExclude', '') or ''
    parts = {p.strip() for p in str(raw_exclude).replace('，', ',').split(',') if p.strip()}
    snap = update_device_timetable(device_id, config.data, exclude_commands=parts or None)
    logger.info(
        'TimerPlan timetable device=%s needRunning=%s earliest=%s',
        device_id,
        snap.get('needRunning'),
        snap.get('earliestCommand'),
    )

    config.load()
    config.bind('ProalasAiPlanner')
    # bind 后 Scheduler.Enable → 属性名 Scheduler_Enable（非 ProalasAiPlanner_Scheduler_Enable）
    planner_enabled = bool(getattr(config, 'Scheduler_Enable', False))
    if not planner_enabled:
        logger.info('TimerPlan bundle: skip AI planner — ProalasAiPlanner.Scheduler.Enable=false')
    else:
        from module.proalas.feature_gate import check_feature
        from module.proalas.ai_planner.cycle import run_ai_planner_cycle

        allowed, reason = check_feature(config, 'ProalasAiPlanner')
        if allowed:
            logger.info('TimerPlan bundle: AI planner (after materialize)')
            run_ai_planner_cycle(config, trigger='after_timer_plan', skip_task_delay=True)
        else:
            logger.info('TimerPlan bundle: skip AI planner — %s', reason)
