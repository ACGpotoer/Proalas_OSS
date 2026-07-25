# -*- coding: utf-8
"""AI 规划指令 Schema 与白名单校验（仅 red 主动域）。"""
from __future__ import annotations

import re
from typing import Any

from module.proalas.quadrant_policy import (
    extract_red_include,
    is_ai_allowed_set_path,
    is_ai_allowed_task_delay,
)

_PATH_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$')

_PLAN_ACTIONS = frozenset({'run', 'pause', 'wake', 'sleep'})


def normalize_commands(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict) and item.get('op'):
            out.append(dict(item))
    return out


def validate_command(cmd: dict[str, Any], *, red_include: list[str] | None = None) -> tuple[bool, str]:
    include = list(red_include or [])
    op = str(cmd.get('op') or '').strip().lower()

    if op == 'set':
        path = str(cmd.get('path') or '').strip()
        if not _PATH_RE.match(path):
            return False, f'set 路径非法: {path}'
        if 'value' not in cmd:
            return False, 'set 缺少 value'
        ok, err = is_ai_allowed_set_path(path, include)
        return (True, '') if ok else (False, err)

    if op == 'task_delay':
        task = str(cmd.get('task') or '').strip()
        if not task:
            return False, 'task_delay 缺少 task'
        if cmd.get('minute') is None and cmd.get('target') is None:
            return False, 'task_delay 需要 minute 或 target'
        ok, err = is_ai_allowed_task_delay(task, include)
        return (True, '') if ok else (False, err)

    if op == 'red_patch':
        date = str(cmd.get('date') or '').strip()
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            return False, f'red_patch date 非法: {date}'
        runtime = cmd.get('runtime')
        if runtime is not None and not isinstance(runtime, dict):
            return False, 'red_patch runtime 必须为 object'
        return True, ''

    if op == 'plan_upsert':
        return False, 'plan_upsert 已废弃：请用 red_patch 写红区主动任务'

    return False, f'未知 op: {op}'


def validate_commands(
    commands: list[dict[str, Any]],
    *,
    red_include: list[str] | None = None,
    red_block: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    include = list(red_include or [])
    if not include and red_block:
        include = extract_red_include(red_block)
    ok_list: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, cmd in enumerate(commands):
        ok, err = validate_command(cmd, red_include=include)
        if ok:
            ok_list.append(cmd)
        else:
            errors.append(f'#{i + 1}: {err}')
    if not include and ok_list:
        errors.insert(0, 'AI 红区 Include 为空（无已启用可调任务），已拒绝全部指令')
        return [], errors
    return ok_list, errors


def command_to_label(cmd: dict[str, Any]) -> str:
    op = str(cmd.get('op') or '')
    if op == 'set':
        return f"set {cmd.get('path')} = {cmd.get('value')!r}"
    if op == 'task_delay':
        if cmd.get('target'):
            return f"task_delay {cmd.get('task')} → {cmd.get('target')}"
        return f"task_delay {cmd.get('task')} +{cmd.get('minute')}min"
    if op == 'red_patch':
        return f"red_patch {cmd.get('date')} runtime={cmd.get('runtime')!r}"
    if op == 'plan_upsert':
        return f"plan {cmd.get('date')} {cmd.get('action')} 「{cmd.get('note') or ''}」"
    return str(cmd)
