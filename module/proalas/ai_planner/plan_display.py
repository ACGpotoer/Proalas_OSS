# -*- coding: utf-8 -*-
"""将最近一次定时规划格式化为 WebUI 结构化视图。"""
from __future__ import annotations

from typing import Any

from module.proalas.ai_planner.command_schema import command_to_label, normalize_commands
from module.proalas.ai_planner.history_store import list_history, load_session_cache
from module.proalas.ai_planner.strategies import strategy_label

_EMPTY_HINT = '尚无定时规划。系统每天自动生成 2 次（约每 12 小时），请稍后查看。'


def _resolve_latest_payload(device_id: str) -> dict[str, Any]:
    cache = load_session_cache(device_id)
    if cache.get('summary') or cache.get('commands'):
        return cache

    for row in list_history(device_id, limit=10):
        if str(row.get('mode') or '') in ('scheduled', 'auto'):
            return row

    for row in list_history(device_id, limit=1):
        return row

    return {}


def command_display_row(cmd: dict[str, Any], index: int) -> dict[str, str]:
    """单条指令 → WebUI 行（类型 / 对象 / 值）。"""
    op = str(cmd.get('op') or '').strip().lower()
    if op == 'set':
        return {
            'index': str(index),
            'kind': '修改配置',
            'target': str(cmd.get('path') or '—'),
            'value': repr(cmd.get('value')),
            'raw': command_to_label(cmd),
        }
    if op == 'task_delay':
        if cmd.get('target'):
            value = f"→ {cmd.get('target')}"
        else:
            minute = cmd.get('minute')
            value = f"+{minute} min" if minute is not None else '—'
        return {
            'index': str(index),
            'kind': '推迟任务',
            'target': str(cmd.get('task') or '—'),
            'value': value,
            'raw': command_to_label(cmd),
        }
    if op == 'red_patch':
        return {
            'index': str(index),
            'kind': '红区补丁',
            'target': str(cmd.get('date') or '—'),
            'value': repr(cmd.get('runtime')),
            'raw': command_to_label(cmd),
        }
    return {
        'index': str(index),
        'kind': op or '指令',
        'target': '—',
        'value': command_to_label(cmd),
        'raw': command_to_label(cmd),
    }


def build_plan_view(device_id: str) -> dict[str, Any]:
    """结构化规划视图（供 WebUI 卡片渲染）。"""
    payload = _resolve_latest_payload(device_id)
    if not payload:
        return {
            'empty': True,
            'hint': _EMPTY_HINT,
            'at': '—',
            'strategy': '',
            'strategy_label': '—',
            'applied': False,
            'applied_label': '—',
            'summary': '',
            'commands': [],
            'warnings': [],
        }

    commands = normalize_commands(payload.get('commands'))
    applied = bool(payload.get('applied'))
    return {
        'empty': False,
        'hint': '',
        'at': str(payload.get('at') or payload.get('updatedAt') or '—'),
        'strategy': str(payload.get('strategy') or ''),
        'strategy_label': strategy_label(str(payload.get('strategy') or '')),
        'applied': applied,
        'applied_label': '已写入配置' if applied else '仅记录（未应用）',
        'summary': str(payload.get('summary') or '（无摘要）').strip(),
        'commands': [command_display_row(cmd, i) for i, cmd in enumerate(commands, 1)],
        'warnings': [str(w) for w in (payload.get('warnings') or []) if str(w).strip()],
    }


def _format_block(payload: dict[str, Any]) -> str:
    if not payload:
        return _EMPTY_HINT

    commands = normalize_commands(payload.get('commands'))
    command_rows = [command_display_row(cmd, i) for i, cmd in enumerate(commands, 1)]
    warnings = [str(w) for w in (payload.get('warnings') or []) if str(w).strip()]

    lines = [
        f"生成时间：{payload.get('at') or payload.get('updatedAt') or '—'}",
        f"策略：{strategy_label(str(payload.get('strategy') or ''))}",
        f"应用状态：{'已写入配置' if payload.get('applied') else '仅记录（未应用）'}",
        '',
        '【规划摘要】',
        str(payload.get('summary') or '（无摘要）'),
        '',
        '【具体改动】',
    ]
    if command_rows:
        for row in command_rows:
            lines.append(f"{row['index']}. {row['raw']}")
    else:
        lines.append('（无指令）')

    if warnings:
        lines.extend(['', '【提示】'])
        lines.extend(f'- {w}' for w in warnings)

    return '\n'.join(lines)


def get_latest_plan_display(device_id: str) -> str:
    """纯文本 fallback（日志 / 导出）。"""
    payload = _resolve_latest_payload(device_id)
    return _format_block(payload)
