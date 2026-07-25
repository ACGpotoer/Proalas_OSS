# -*- coding: utf-8 -*-
"""组装 AI 规划上下文（脱敏摘要，不含 LLM Key / Emulator 敏感字段）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from module.config.deep import deep_get
from module.config.utils import read_file, filepath_config
from module.proalas.plan_schedule_api import list_plan_entries
from module.proalas.time_table import build_device_snapshot, read_device_timetable
from module.proalas_collector.userdata import (
    read_game_resource,
    read_exp_book_meta,
)
from module.proalas.ai_planner.custom_event_main import (
    custom_event_main_context_note,
    is_custom_event_main_enabled,
)
from module.proalas.fleet_team_roles import team_roles_context_note, team_roles_for_context
from module.proalas.ai_planner.settings import load_ai_planner_settings
from module.proalas.ai_planner.strategies import normalize_strategy, strategy_prompt_hint

# 不参与 highlights 的块
_SKIP_HIGHLIGHT_KEYS = frozenset({
    'Scheduler', 'Storage', 'Emotion', 'DropRecord',
})

# 敏感字段不上传
_SENSITIVE_KEYS = frozenset({
    'Serial', 'Password', 'PackageName', 'ScreenshotMethod', 'ControlMethod',
    'OnePushConfig', 'Error_OnePushConfig',
})


def _parse_synced_at(text: str) -> Optional[datetime]:
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(str(text).strip()[:19], fmt)
        except ValueError:
            continue
    return None


def _task_highlights(task_body: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in (task_body or {}).items():
        if key in _SKIP_HIGHLIGHT_KEYS or key in _SENSITIVE_KEYS:
            continue
        if isinstance(val, dict):
            nested = {
                k: v for k, v in val.items()
                if k not in _SENSITIVE_KEYS and not isinstance(v, (dict, list))
            }
            if nested:
                out[key] = nested
        elif not isinstance(val, (list, dict)):
            out[key] = val
    return out


def build_plan_context(device_id: str, *, strategy_id: str = 'conservative') -> dict[str, Any]:
    """
    构建发往网关的 context 包（不含 API Key）。
    """
    device_id = str(device_id or '').strip()
    strategy = normalize_strategy(strategy_id)
    settings = load_ai_planner_settings()
    config_path = filepath_config(device_id)
    config_data = read_file(config_path)
    if not isinstance(config_data, dict):
        config_data = {}

    game_resource = read_game_resource(device_id)
    synced_at = str(game_resource.get('syncedAt') or '')
    synced_dt = _parse_synced_at(synced_at)
    stale_hours = settings.stale_collector_hours
    collector_stale = False
    if synced_dt is None:
        collector_stale = True
    else:
        collector_stale = datetime.now() - synced_dt > timedelta(hours=stale_hours)

    enabled_tasks = []
    for task_name, body in config_data.items():
        if not isinstance(body, dict):
            continue
        sched = body.get('Scheduler')
        if not isinstance(sched, dict) or not sched.get('Enable'):
            continue
        command = str(sched.get('Command') or task_name)
        next_run = sched.get('NextRun')
        if hasattr(next_run, 'strftime'):
            next_run = next_run.strftime('%Y-%m-%d %H:%M:%S')
        enabled_tasks.append({
            'taskName': task_name,
            'command': command,
            'nextRun': str(next_run or ''),
            'highlights': _task_highlights(body),
        })

    timetable_snap = read_device_timetable(device_id)
    if not timetable_snap and config_data:
        timetable_snap = build_device_snapshot(device_id, config_data)

    today = datetime.now().date()
    week_end = today + timedelta(days=7)
    plan_entries = []
    for entry in list_plan_entries(device_id):
        d = str(entry.get('date') or '')
        try:
            ed = datetime.strptime(d, '%Y-%m-%d').date()
        except ValueError:
            continue
        if today <= ed <= week_end:
            plan_entries.append({
                'date': d,
                'action': entry.get('action'),
                'note': entry.get('note'),
                'source': entry.get('source'),
            })

    fleet = _read_proalas_block(device_id, 'ProalasData', 'FleetStrength')
    auto_break = _read_proalas_block(device_id, 'ProalasData', 'AutoBreak')
    from module.proalas.plan_server_quadrants import get_red_quadrant
    from module.proalas.ai_planner.red_include_defaults import resolve_effective_red_include

    today_str = today.strftime('%Y-%m-%d')
    red_block = get_red_quadrant(device_id, today_str)
    red_include, red_include_source = resolve_effective_red_include(
        device_id, today_str, config_data=config_data,
    )

    custom_event_main = is_custom_event_main_enabled(config_data=config_data)
    planning_constraints: list[str] = [team_roles_context_note()]
    if custom_event_main:
        planning_constraints.append(custom_event_main_context_note())

    teams_summary = []
    for team in (fleet.get('teams') or [])[:6]:
        if not isinstance(team, dict):
            continue
        teams_summary.append({
            'team': team.get('team'),
            'backPower': team.get('backPower'),
            'frontPower': team.get('frontPower'),
            'shipCount': len(team.get('ships') or []),
        })

    return {
        'deviceId': device_id,
        'generatedAt': datetime.now().replace(microsecond=0).isoformat(timespec='seconds'),
        'rulesVersion': settings.rules_version or None,
        'strategyId': strategy,
        'strategyHint': strategy_prompt_hint(strategy),
        'customEventMain': custom_event_main,
        'planningConstraints': planning_constraints,
        'resources': {
            'oil': game_resource.get('oil'),
            'money': game_resource.get('money'),
            'cube': game_resource.get('cube'),
            'rmb': game_resource.get('Rmb'),
            'actPt': game_resource.get('Act-Pt'),
            'boatRate': game_resource.get('BoatRate'),
            'boatMax': game_resource.get('BoatMax'),
            'syncedAt': synced_at,
            'stale': collector_stale,
            'staleThresholdHours': stale_hours,
        },
        'fleets': {
            'teams': teams_summary,
            'teamRoles': team_roles_for_context(),
        },
        'autoBreak': auto_break,
        'expBook': read_exp_book_meta(device_id),
        'enabledTasks': enabled_tasks,
        'timetable': timetable_snap or {},
        'planEntriesThisWeek': plan_entries,
        'redQuadrant': red_block,
        'redInclude': red_include,
        'redIncludeSource': red_include_source,
        'redIncludeFallback': red_include_source == 'derived',
        'quadrantPolicy': {
            'aiOwns': 'red',
            'serverOwns': ['yellow', 'green', 'blue'],
            'redFromCalendar': False,
            'allowedOps': ['set', 'task_delay', 'red_patch'],
            'forbiddenOps': ['plan_upsert'],
        },
        'server': str(config_data.get('Alas', {}).get('Emulator', {}).get('ServerName') or ''),
    }


def _read_proalas_block(device_id: str, *keys: str) -> dict[str, Any]:
    data = read_file(filepath_config(device_id))
    if not isinstance(data, dict):
        return {}
    block = deep_get(data, list(keys), None)
    return dict(block) if isinstance(block, dict) else {}
