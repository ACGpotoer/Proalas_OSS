# -*- coding: utf-8 -*-
"""在本机安全执行 AI 规划指令（仅 red 主动域）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.proalas.ai_planner.command_schema import validate_commands
from module.proalas.plan_schedule_store import upsert_device_day_override
from module.proalas.plan_server_quadrants import get_red_quadrant
from module.proalas.ai_planner.red_include_defaults import resolve_effective_red_include


def _parse_target(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(text[:19], fmt).replace(microsecond=0)
        except ValueError:
            continue
    return None


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def apply_commands(
    device_id: str,
    commands: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    on_date: str | None = None,
) -> dict[str, Any]:
    """
    将 red 域指令写入 config/{device_id}.json（task_delay / 有限 set / red_patch）。
    黄/绿/蓝由 ProalasActivitySync + sync gateway 物化，AI 不可改。
    """
    device_id = str(device_id or '').strip()
    date_str = str(on_date or _today_str())
    path = filepath_config(device_id)
    data = read_file(path)
    if not isinstance(data, dict):
        red_block = get_red_quadrant(device_id, date_str)
        red_include, _ = resolve_effective_red_include(device_id, date_str, config_data={})
        return {
            'applied': 0,
            'skipped': len(commands),
            'errors': ['配置文件不存在'],
            'details': [],
            'dryRun': dry_run,
            'redInclude': red_include,
        }

    red_block = get_red_quadrant(device_id, date_str)
    red_include, _ = resolve_effective_red_include(device_id, date_str, config_data=data)

    valid, schema_errors = validate_commands(commands, red_include=red_include, red_block=red_block)
    if schema_errors:
        return {
            'applied': 0,
            'skipped': len(commands),
            'errors': schema_errors,
            'details': [],
            'dryRun': dry_run,
            'redInclude': red_include,
        }

    proalas_backup = deep_get(data, ['ProalasData'], None)
    details: list[str] = []
    errors: list[str] = []
    applied = 0

    for cmd in valid:
        op = str(cmd.get('op') or '').lower()
        try:
            if op == 'set':
                path_keys = str(cmd.get('path') or '').split('.')
                deep_set(data, keys=path_keys, value=cmd.get('value'))
                details.append(f'set {cmd.get("path")}')
                applied += 1
            elif op == 'task_delay':
                task = str(cmd.get('task') or '').strip()
                sched_path = [task, 'Scheduler', 'NextRun']
                if cmd.get('target') is not None:
                    run_at = _parse_target(cmd.get('target'))
                    if run_at is None:
                        raise ValueError(f'target 无法解析: {cmd.get("target")}')
                else:
                    minute = int(cmd.get('minute') or 0)
                    run_at = datetime.now().replace(microsecond=0) + timedelta(minutes=minute)
                if task not in data or not isinstance(data.get(task), dict):
                    data[task] = data.get(task) if isinstance(data.get(task), dict) else {}
                deep_set(data, keys=sched_path, value=run_at.strftime('%Y-%m-%d %H:%M:%S'))
                details.append(f'task_delay {task} → {run_at}')
                applied += 1
            elif op == 'red_patch':
                patch_date = str(cmd.get('date') or date_str)
                payload: dict[str, Any] = {'red': {}}
                if cmd.get('runtime') is not None:
                    payload['red']['runtime'] = dict(cmd.get('runtime') or {})
                if cmd.get('note'):
                    payload['red']['note'] = str(cmd.get('note'))
                if dry_run:
                    details.append(f'red_patch {patch_date} (dry-run)')
                    applied += 1
                    continue
                upsert_device_day_override(device_id, patch_date, payload, source='ai')
                details.append(f'red_patch {patch_date}')
                applied += 1
        except Exception as e:
            errors.append(f'{op}: {e}')
            logger.warning('AiPlanner apply failed cmd=%s err=%s', cmd, e)

    if dry_run:
        return {
            'applied': applied,
            'skipped': len(valid) - applied,
            'errors': errors,
            'details': details,
            'dryRun': True,
            'redInclude': red_include,
        }

    if proalas_backup is not None:
        deep_set(data, keys=['ProalasData'], value=proalas_backup)

    red_plan = {
        'date': date_str,
        'include': red_include,
        'appliedAt': datetime.now().isoformat(timespec='seconds'),
        'details': details[:20],
    }
    proalas = deep_get(data, ['ProalasData'], {}) or {}
    if isinstance(proalas, dict):
        proalas['RedPlan'] = red_plan
        deep_set(data, keys=['ProalasData'], value=proalas)

    if applied > 0 and not errors:
        write_file(path, data)
        logger.info('AiPlanner red-only applied %s commands device=%s include=%s', applied, device_id, red_include)
    elif applied > 0 and errors:
        write_file(path, data)
        logger.warning('AiPlanner partial apply device=%s errors=%s', device_id, errors)

    return {
        'applied': applied,
        'skipped': len(valid) - applied,
        'errors': errors,
        'details': details,
        'dryRun': False,
        'redInclude': red_include,
    }
