# -*- coding: utf-8 -*-
"""活动1/2、主线1/2 用户自定义模式：AI 规划跳过对这些任务的修改。"""
from __future__ import annotations

from typing import Any

from module.config.deep import deep_get

# 活动1、活动2、主线1、主线2（非「活动12/主线12」）
LOCKED_TASKS = frozenset({'Event', 'Event2', 'Main', 'Main2'})


def is_custom_event_main_enabled(config: Any = None, *, config_data: dict | None = None) -> bool:
    if config is not None:
        val = getattr(config, 'ProalasAiPlanner_CustomEventMain', None)
        if val is not None:
            return bool(val)
    if isinstance(config_data, dict):
        return bool(
            deep_get(config_data, ['ProalasAiPlanner', 'ProalasAiPlanner', 'CustomEventMain'], False)
        )
    return False


def path_targets_locked_task(path: str) -> bool:
    path = str(path or '').strip()
    if not path:
        return False
    return path.split('.', 1)[0] in LOCKED_TASKS


def task_is_locked(task: str) -> bool:
    return str(task or '').strip() in LOCKED_TASKS


def _sanitize_red_patch(cmd: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    runtime = cmd.get('runtime')
    if not isinstance(runtime, dict):
        return cmd, None

    removed: list[str] = []
    new_runtime = dict(runtime)

    include = runtime.get('Include')
    if isinstance(include, list):
        kept_include = []
        for item in include:
            name = str(item).strip()
            if task_is_locked(name):
                removed.append(name)
            else:
                kept_include.append(item)
        if removed:
            new_runtime['Include'] = kept_include

    for key, val in runtime.items():
        if key == 'Include':
            continue
        if isinstance(val, dict):
            nested_removed = [k for k in val if task_is_locked(str(k))]
            if nested_removed:
                new_val = {k: v for k, v in val.items() if not task_is_locked(str(k))}
                new_runtime[key] = new_val
                removed.extend(nested_removed)

    if not removed:
        return cmd, None

    if not new_runtime or (
        len(new_runtime) == 1
        and isinstance(new_runtime.get('Include'), list)
        and not new_runtime.get('Include')
    ):
        return None, f'活动/主线自定义：跳过 red_patch（涉及 {", ".join(sorted(set(removed)))}）'

    new_cmd = dict(cmd)
    new_cmd['runtime'] = new_runtime
    return new_cmd, f'活动/主线自定义：red_patch 已移除 {", ".join(sorted(set(removed)))}'


def filter_locked_commands(
    commands: list[dict[str, Any]],
    *,
    enabled: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled or not commands:
        return list(commands or []), []

    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        op = str(cmd.get('op') or '').lower()
        if op == 'set':
            path = str(cmd.get('path') or '').strip()
            if path_targets_locked_task(path):
                warnings.append(f'活动/主线自定义：跳过 set {path}')
                continue
        elif op == 'task_delay':
            task = str(cmd.get('task') or '').strip()
            if task_is_locked(task):
                warnings.append(f'活动/主线自定义：跳过 task_delay {task}')
                continue
        elif op == 'red_patch':
            sanitized, warn = _sanitize_red_patch(cmd)
            if warn:
                warnings.append(warn)
            if sanitized is not None:
                kept.append(sanitized)
            continue
        kept.append(cmd)
    return kept, warnings


def custom_event_main_context_note() -> str:
    return (
        '用户已开启「活动与主线自定义」：禁止对 Event、Event2、Main、Main2 '
        '（活动1/2、主线1/2）做任何 set、task_delay 或 red_patch 修改。'
    )
