# -*- coding: utf-8 -*-
"""
AI 红区 Include（红不由全局日历画，由 AiPlanner 决策并落盘）。

优先级：
  1. PlanSchedule 设备 override 中 AI red_patch 写入的 runtime.Include
  2. 同日 ProalasData.RedPlan.include（上次 apply 记录）
  3. 从 config 推导「当前可调度的任务名」（已 Enable 且属 AI 域）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.deep import deep_get
from module.config.utils import filepath_config, read_file
from module.logger import logger
from module.proalas.plan_schedule_store import get_device_day_override
from module.proalas.quadrant_policy import extract_red_include

# 与 迁移文档/config路径对照-0D001范本.md §4~§7 对齐（task_delay / set 顶层任务名）
_AI_RED_TASK_NAMES = (
    # 出击
    'Main', 'Main2', 'Main3',
    'Event', 'Event2', 'EventA', 'EventB', 'EventC', 'EventD', 'EventSp',
    'Raid', 'RaidDaily', 'Hard', 'GemsFarming', 'Exercise',
    # 日常
    'Commission', 'Tactical', 'Research', 'Dorm', 'Meowfficer', 'Guild',
    'Reward', 'Daily', 'Awaken', 'ShopFrequent', 'ShopOnce', 'Freebies',
    'Minigame', 'Gacha',
    # Opsi（§6.2 全表）
    'OpsiExplore', 'OpsiDaily', 'OpsiObscure', 'OpsiAbyssal', 'OpsiStronghold',
    'OpsiMonthBoss', 'OpsiAshBeacon', 'OpsiAshAssist', 'OpsiShop', 'OpsiVoucher',
    'OpsiMeowfficerFarming', 'OpsiHazard1Leveling', 'OpsiCrossMonth', 'OpsiArchive',
    # ProAlas
    'ProalasAutoBreak', 'ProalasAutoEquip', 'ProalasAutoEventShop', 'ProalasAutoExpBook',
    'ProalasGetExpUseExp', 'ProalasCollector', 'ProalasFleetStrength',
    'ProalasAutoFleetChange', 'ProalasGachaCheck',
)


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _enabled_task_names(config_data: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for task_name, body in (config_data or {}).items():
        if not isinstance(body, dict):
            continue
        sched = body.get('Scheduler')
        if isinstance(sched, dict) and sched.get('Enable'):
            out.add(str(task_name))
    return out


def build_ai_red_include(config_data: dict[str, Any]) -> list[str]:
    """从 config 推导本周期 AI 可调度的任务名（不要求日历 red）。"""
    enabled = _enabled_task_names(config_data)
    known = set(_AI_RED_TASK_NAMES)
    out: list[str] = []
    for name in _AI_RED_TASK_NAMES:
        if name in enabled:
            out.append(name)
    for name in sorted(enabled):
        if name in out:
            continue
        if name in known:
            out.append(name)
        elif name.startswith('Opsi') or name.startswith('Proalas'):
            out.append(name)
    return out


def _include_from_red_plan(config_data: dict[str, Any], date_str: str) -> list[str]:
    red_plan = deep_get(config_data, ['ProalasData', 'RedPlan'], {}) or {}
    if not isinstance(red_plan, dict):
        return []
    if str(red_plan.get('date') or '') != date_str:
        return []
    raw = red_plan.get('include') or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def resolve_effective_red_include(
    device_id: str,
    date_str: str | None = None,
    *,
    config_data: dict[str, Any] | None = None,
) -> tuple[list[str], str]:
    """
    返回 (Include 列表, source)。
    source: ai_override | red_plan | derived
    """
    device_id = str(device_id or '').strip()
    date_str = str(date_str or _today_str())

    if config_data is None:
        config_data = read_file(filepath_config(device_id))
    if not isinstance(config_data, dict):
        config_data = {}

    override = get_device_day_override(device_id, date_str)
    red_block = override.get('red') if isinstance(override.get('red'), dict) else {}
    include = extract_red_include(red_block if isinstance(red_block, dict) else {})
    if include:
        return include, 'ai_override'

    include = _include_from_red_plan(config_data, date_str)
    if include:
        return include, 'red_plan'

    derived = build_ai_red_include(config_data)
    if derived:
        logger.info(
            'AiPlanner red Include 由 config 推导 device=%s date=%s tasks=%s',
            device_id,
            date_str,
            derived,
        )
    return derived, 'derived'
