# -*- coding: utf-8 -*-
"""三档策略配置宏：YAML → executor 指令 / DAP change 行。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from module.logger import logger
from module.proalas.ai_planner.strategies import STRATEGIES, normalize_strategy

_PRESETS_PATH = Path(__file__).resolve().parent / 'strategy_presets.yaml'


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {}
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning('strategy_presets load failed: %s', e)
        return {}
    return raw if isinstance(raw, dict) else {}


def _normalize_commands(raw_cmds: Any, *, strategy_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw_cmds, list):
        return []
    out: list[dict[str, Any]] = []
    today = datetime.now().strftime('%Y-%m-%d')
    for item in raw_cmds:
        if not isinstance(item, dict):
            continue
        cmd = dict(item)
        op = str(cmd.get('op') or '').lower()
        if op == 'plan_upsert' and str(cmd.get('date') or '').strip().lower() == 'auto':
            cmd['date'] = today
        if op == 'set' and str(cmd.get('path') or '').endswith('Strategy'):
            cmd['value'] = normalize_strategy(cmd.get('value') or strategy_id)
        out.append(cmd)
    return out


def load_preset_commands(strategy_id: str) -> list[dict[str, Any]]:
    strategy_id = normalize_strategy(strategy_id)
    data = _read_yaml(_PRESETS_PATH)
    presets = data.get('presets')
    if not isinstance(presets, dict):
        return []
    row = presets.get(strategy_id)
    if not isinstance(row, dict):
        return []
    return _normalize_commands(row.get('commands'), strategy_id=strategy_id)


def list_preset_ids() -> list[str]:
    data = _read_yaml(_PRESETS_PATH)
    presets = data.get('presets')
    if not isinstance(presets, dict):
        return []
    return [k for k in presets if k in STRATEGIES]


def apply_strategy_preset(
    device_id: str,
    strategy_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    from module.proalas.ai_planner.executor import apply_commands

    strategy_id = normalize_strategy(strategy_id)
    commands = load_preset_commands(strategy_id)
    if not commands:
        return {
            'applied': 0,
            'skipped': 0,
            'errors': [f'未找到策略宏: {strategy_id}'],
            'details': [],
            'dryRun': dry_run,
            'strategyId': strategy_id,
        }
    result = apply_commands(device_id, commands, dry_run=dry_run)
    result['strategyId'] = strategy_id
    return result


def _json_literal(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def preset_to_change_lines(device_id: str, strategy_id: str) -> list[str]:
    """供 DAP semantic_translate 展开为 change 行（仅 set；task_delay/plan 在 Alas 侧 apply）。"""
    device_id = str(device_id).upper().strip()
    lines: list[str] = []
    for cmd in load_preset_commands(strategy_id):
        op = str(cmd.get('op') or '').lower()
        if op != 'set':
            continue
        path = str(cmd.get('path') or '').strip()
        if not path:
            continue
        # change 0E021 ProalasAiPlanner Strategy conservative
        segments = path.split('.')
        lines.append(f'change {device_id} {" ".join(segments)} {_json_literal(cmd.get("value"))}')
    return lines
