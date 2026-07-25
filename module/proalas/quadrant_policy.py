# -*- coding: utf-8 -*-
"""
计划表四色写入权：
  黄 / 绿 / 蓝 → 服务器（GlobalActivityCalendar + sync gateway / HostAgent）
  红           → 本机 AiPlanner（**不由日历画**；每 ~12h 生成并落盘 PlanSchedule/RedPlan）
合并优先级（物化）：蓝 > 黄 > 绿；红不参与物化，仅排程微调。
"""
from __future__ import annotations

from typing import Any

QUADRANT_KEYS = ('yellow', 'red', 'green', 'blue')
SERVER_QUADRANTS = frozenset({'yellow', 'green', 'blue'})
AI_QUADRANT = 'red'
MERGE_PRIORITY = ('blue', 'yellow', 'green')

# AiPlanner set 允许的路径前缀（Campaign.Event / Scheduler.Enable 等仍禁止）
# 对齐：ProAlas/迁移文档/config路径对照-0D001范本.md §4~§7
_AI_SET_TASK_PREFIXES = (
    'Daily.',
    'Hard.',
    'Commission.',
    'Research.',
    'Reward.',
    'Freebies.',
    'Tactical.',
    'Dorm.',
    'Meowfficer.',
    'EventGeneral.',
    'Event.',
    'Event2.',
    'EventA.',
    'EventB.',
    'EventC.',
    'EventD.',
    'EventSp.',
    'Main.',
    'Main2.',
    'Main3.',
    'Raid.',
    'RaidDaily.',
    'GemsFarming.',
    'Exercise.',
    'Opsi',
    'OpsiGeneral.',
    'ProalasAutoBreak.',
    'ProalasAutoEquip.',
    'ProalasAutoEventShop.',
    'ProalasAutoExpBook.',
    'ProalasGetExpUseExp.',
    'ProalasCollector.',
    'ProalasFleetStrength.',
    'ProalasAutoFleetChange.',
)

# 服务器独占：AI 禁止 set / task_delay 触及
_AI_FORBIDDEN_PATH_PREFIXES = (
    'Alas.',
    'Event.Campaign.',
    'Event2.Campaign.',
    'EventA.Campaign.',
    'EventB.Campaign.',
    'EventC.Campaign.',
    'EventD.Campaign.',
    'EventSp.Campaign.',
    'Main.Campaign.',
    'Main2.Campaign.',
    'Main3.Campaign.',
)

_AI_FORBIDDEN_PATH_EXACT = frozenset({
    'Event.Campaign.Event',
    'Event2.Campaign.Event',
    'Event.Scheduler.Enable',
    'Event2.Scheduler.Enable',
    'Main.Scheduler.Enable',
    'Main2.Scheduler.Enable',
    'Main3.Scheduler.Enable',
    'Daily.Scheduler.Enable',
    'Commission.Scheduler.Enable',
    'Research.Scheduler.Enable',
    'Gacha.Scheduler.Enable',
    'ProalasAutoFleetChange.Team1Type',
    'ProalasAutoFleetChange.Team2Type',
    'ProalasAutoFleetChange.Team3Type',
    'ProalasAutoFleetChange.Team4Type',
    'ProalasAutoFleetChange.Team5Type',
    'ProalasAutoFleetChange.Team6Type',
})

_OVERRIDE_SOURCE_AI = frozenset({'ai', 'ai_planner'})
_OVERRIDE_SOURCE_SERVER = frozenset({'server', 'sync', 'host', 'manual'})


def normalize_override_source(source: str) -> str:
    return str(source or 'manual').strip().lower()


def validate_override_quadrants(payload: dict[str, Any], *, source: str) -> list[str]:
    """设备 overrides 写入校验。返回错误列表，空=通过。"""
    src = normalize_override_source(source)
    errors: list[str] = []
    for quadrant, block in (payload or {}).items():
        q = str(quadrant)
        if q not in QUADRANT_KEYS:
            errors.append(f'未知象限: {q}')
            continue
        if not isinstance(block, dict):
            errors.append(f'{q} 必须为 object')
            continue
        if src in _OVERRIDE_SOURCE_AI and q != AI_QUADRANT:
            errors.append(f'AI 仅可写 red 象限，禁止 {q}')
        if src in _OVERRIDE_SOURCE_SERVER and q == AI_QUADRANT:
            errors.append('服务器同步不可写 red（留给 AiPlanner）')
    return errors


def extract_red_include(red_block: dict[str, Any] | None) -> list[str]:
    if not isinstance(red_block, dict):
        return []
    runtime = red_block.get('runtime')
    if not isinstance(runtime, dict):
        return []
    raw = runtime.get('Include') or runtime.get('include') or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def task_in_red_include(task: str, include: list[str]) -> bool:
    task = str(task or '').strip()
    if not task or not include:
        return False
    if task in include:
        return True
    for name in include:
        if not name:
            continue
        if task == name or task.startswith(name):
            return True
        if name == 'Opsi' and task.startswith('Opsi'):
            return True
    return False


def is_ai_allowed_set_path(path: str, include: list[str]) -> tuple[bool, str]:
    path = str(path or '').strip()
    if not path:
        return False, 'path 为空'
    if path in _AI_FORBIDDEN_PATH_EXACT:
        return False, f'服务器域字段禁止 AI 修改: {path}'
    for prefix in _AI_FORBIDDEN_PATH_PREFIXES:
        if path.startswith(prefix):
            return False, f'服务器域禁止: {path}'
    if '.Scheduler.Enable' in path or path.endswith('.Scheduler.Enable'):
        return False, 'Scheduler.Enable 由服务器日历物化'
    if '.Campaign.Event' in path:
        return False, 'Campaign.Event 由服务器蓝区物化'
    task = path.split('.', 1)[0]
    if not task_in_red_include(task, include):
        return False, f'任务 {task} 不在今日 red.runtime.Include'
    if not any(path.startswith(p) for p in _AI_SET_TASK_PREFIXES):
        return False, f'set 路径不在 AI 允许前缀: {path}'
    return True, ''


def is_ai_allowed_task_delay(task: str, include: list[str]) -> tuple[bool, str]:
    task = str(task or '').strip()
    if not task_in_red_include(task, include):
        return False, f'task_delay 仅允许 red Include 内任务: {task}'
    return True, ''


def merge_scheduler_maps(*layers: dict[str, Any]) -> dict[str, bool]:
    """高优先级层在后：blue 应最后传入以覆盖 yellow。"""
    out: dict[str, bool] = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for k, v in layer.items():
            out[str(k)] = bool(v)
    return out
