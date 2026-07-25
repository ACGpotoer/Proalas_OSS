# -*- coding: utf-8 -*-
"""AI 规划统一执行周期（TimerPlan 串行 + Scheduler 去重 + 本地门禁）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.logger import logger
from module.proalas.ai_planner.context_builder import build_plan_context
from module.proalas.ai_planner.gateway_client import AiPlannerGatewayError, request_plan
from module.proalas.ai_planner.command_schema import normalize_commands
from module.proalas.ai_planner.executor import apply_commands
from module.proalas.ai_planner.history_store import append_history, load_session_cache, save_session_cache
from module.proalas.ai_planner.custom_event_main import filter_locked_commands, is_custom_event_main_enabled
from module.proalas.ai_planner.post_process import post_process_commands
from module.proalas.ai_planner.settings import load_ai_planner_settings
from module.proalas.ai_planner.strategies import normalize_strategy, strategy_label
from module.proalas.ai_planner.strategy_switch import effective_auto_apply

# Scheduler 独立触发：距上次规划不足此间隔则跳过（TimerPlan 触发不受限）
MIN_PLAN_INTERVAL_MINUTES = 600
# 12 小时一次 ≈ 每天 2 次
_SCHEDULE_INTERVAL_MINUTES = 720


def _parse_dt(text: Any) -> datetime | None:
    if not text:
        return None
    raw = str(text).strip().replace(' ', 'T')
    try:
        return datetime.fromisoformat(raw[:19]).replace(microsecond=0)
    except ValueError:
        return None


def should_skip_scheduler_cycle(device_id: str) -> bool:
    """Scheduler 触发时：若 TimerPlan 刚跑过规划则跳过，避免双跑。"""
    cache = load_session_cache(device_id)
    last_at = _parse_dt(cache.get('at') or cache.get('updatedAt'))
    if last_at is None:
        return False
    minutes = (datetime.now() - last_at).total_seconds() / 60.0
    return minutes < MIN_PLAN_INTERVAL_MINUTES


def run_ai_planner_cycle(
    config,
    *,
    trigger: str = 'scheduler',
    skip_task_delay: bool = False,
) -> dict[str, Any]:
    """
    执行一次 AI 规划周期。

    trigger:
      - after_timer_plan: TimerPlan 物化完成后串行调用
      - scheduler: ProalasAiPlanner 独立 Scheduler（带去重）
    """
    device_id = str(getattr(config, 'config_name', '') or 'alas')
    result: dict[str, Any] = {
        'deviceId': device_id,
        'trigger': trigger,
        'skipped': False,
        'applied': False,
        'commandCount': 0,
    }

    if trigger == 'scheduler' and should_skip_scheduler_cycle(device_id):
        logger.info(
            'ProalasAiPlanner skip scheduler cycle (last plan within %s min) device=%s',
            MIN_PLAN_INTERVAL_MINUTES,
            device_id,
        )
        result['skipped'] = True
        result['reason'] = 'duplicate_interval'
        if not skip_task_delay:
            config.task_delay(minute=_SCHEDULE_INTERVAL_MINUTES)
        return result

    settings = load_ai_planner_settings(force=True)
    if not settings.configured:
        logger.warning('ProalasAiPlanner 未配置 mumucontrol/ai_planner.yaml')
        result['skipped'] = True
        result['reason'] = 'not_configured'
        if not skip_task_delay and trigger == 'scheduler':
            config.task_delay(minute=_SCHEDULE_INTERVAL_MINUTES)
        return result

    strategy = normalize_strategy(getattr(config, 'ProalasAiPlanner_Strategy', ''))
    auto_apply = effective_auto_apply(config)

    context = build_plan_context(device_id, strategy_id=strategy)
    context['strategyId'] = strategy
    if context.get('resources', {}).get('stale'):
        logger.warning('ProalasAiPlanner 资源数据可能过期，apply 将被本地门禁拦截')

    try:
        resp = request_plan(context, strategy_id=strategy)
    except AiPlannerGatewayError as e:
        logger.error('ProalasAiPlanner 网关失败: %s', e)
        result['skipped'] = True
        result['reason'] = 'gateway_error'
        result['error'] = str(e)
        if not skip_task_delay and trigger == 'scheduler':
            config.task_delay(minute=_SCHEDULE_INTERVAL_MINUTES)
        return result

    summary = str(resp.get('summary') or '')
    commands = normalize_commands(resp.get('commands'))
    warnings = list(resp.get('warnings') or [])
    if resp.get('rulesVersionMismatch'):
        client_rv = settings.rules_version or context.get('rulesVersion') or '?'
        gateway_rv = resp.get('rulesVersion') or '?'
        warnings.insert(
            0,
            f'AI 规则版本不一致：客户端 {client_rv}，网关 {gateway_rv}，请同步 prompt_rules.yaml',
        )
        logger.warning(
            'ProalasAiPlanner rulesVersion mismatch client=%s gateway=%s device=%s',
            client_rv,
            gateway_rv,
            device_id,
        )

    custom_event_main = is_custom_event_main_enabled(config)
    if custom_event_main:
        context['customEventMain'] = True
        commands, lock_warnings = filter_locked_commands(commands, enabled=True)
        warnings.extend(lock_warnings)

    if auto_apply:
        commands, pp_warnings = post_process_commands(commands, context, device_id)
        warnings.extend(pp_warnings)
    elif commands:
        warnings.append('AutoApply 关闭，指令仅预览未写入')

    payload = {
        'summary': summary,
        'commands': commands,
        'warnings': warnings,
        'strategy': strategy,
        'applied': False,
        'at': context.get('generatedAt'),
        'trigger': trigger,
        'autoApply': auto_apply,
        'redIncludeSource': context.get('redIncludeSource'),
        'redIncludeFallback': bool(context.get('redIncludeFallback')),
    }
    save_session_cache(device_id, payload)

    applied_result = None
    if auto_apply and commands:
        applied_result = apply_commands(device_id, commands, dry_run=False)
        payload['applied'] = (applied_result or {}).get('applied', 0) > 0
        save_session_cache(device_id, payload)

    append_history(
        device_id,
        summary=summary,
        commands=commands,
        applied=bool(payload.get('applied')),
        warnings=warnings,
        mode=trigger,
        strategy=strategy,
    )

    applied_n = (applied_result or {}).get('applied') if applied_result else 0
    logger.info(
        'ProalasAiPlanner done device=%s trigger=%s strategy=%s label=%s commands=%s applied=%s autoApply=%s',
        device_id,
        trigger,
        strategy,
        strategy_label(strategy),
        len(commands),
        applied_n,
        auto_apply,
    )

    result.update({
        'skipped': False,
        'applied': bool(payload.get('applied')),
        'commandCount': len(commands),
        'appliedCount': applied_n,
        'autoApply': auto_apply,
        'warnings': warnings,
    })

    if not skip_task_delay and trigger == 'scheduler':
        config.task_delay(minute=_SCHEDULE_INTERVAL_MINUTES)
    return result
