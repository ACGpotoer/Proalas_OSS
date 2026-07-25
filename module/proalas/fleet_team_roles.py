# -*- coding: utf-8 -*-
"""ProAlas 六队职能约定：1–2 推图、3–4 练级、5–6 低耗（托管默认写死）。"""
from __future__ import annotations

from typing import Any

TEAM_COUNT = 6

ROLE_PUSH = 'push'
ROLE_LEVEL = 'level'
ROLE_LOW_COST = 'low_cost'

VALID_ROLES = frozenset({ROLE_PUSH, ROLE_LEVEL, ROLE_LOW_COST})

# 产品固定约定（非 Pro+ 不可改）
TEAM_ROLE_DEFAULTS: dict[int, str] = {
    1: ROLE_PUSH,
    2: ROLE_PUSH,
    3: ROLE_LEVEL,
    4: ROLE_LEVEL,
    5: ROLE_LOW_COST,
    6: ROLE_LOW_COST,
}

ROLE_LABEL_ZH: dict[str, str] = {
    ROLE_PUSH: '推图',
    ROLE_LEVEL: '练级',
    ROLE_LOW_COST: '低耗',
}


def default_team_role(team_id: int) -> str:
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return ROLE_PUSH
    return TEAM_ROLE_DEFAULTS.get(tid, ROLE_PUSH)


def _normalize_role(raw: Any, *, fallback: str) -> str:
    role = str(raw or '').strip().lower()
    if role in VALID_ROLES:
        return role
    return fallback


def team_roles_allow_config_override(config: Any) -> bool:
    """仅 Pro+ 允许在 config 中覆盖队伍职能。"""
    from module.proalas.feature_gate import get_effective_plan

    return get_effective_plan(config) == 'pro_plus'


def resolve_team_role(config: Any, team_id: int) -> str:
    """返回该队有效职能；普通/Pro 用户始终为固定约定。"""
    fallback = default_team_role(team_id)
    if not team_roles_allow_config_override(config):
        return fallback
    raw = getattr(config, f'ProalasAutoFleetChange_Team{int(team_id)}Type', fallback)
    return _normalize_role(raw, fallback=fallback)


def resolve_all_team_roles(config: Any) -> dict[int, str]:
    return {tid: resolve_team_role(config, tid) for tid in range(1, TEAM_COUNT + 1)}


def role_label_zh(role: str) -> str:
    return ROLE_LABEL_ZH.get(str(role or '').strip().lower(), str(role or ''))


def team_roles_summary_zh() -> str:
    return '1–2 推图，3–4 练级，5–6 低耗'


def team_roles_context_note() -> str:
    return (
        f'编队职能固定：{team_roles_summary_zh()}。'
        'AI 禁止修改 ProalasAutoFleetChange.Team*Type。'
    )


def team_roles_for_context(config: Any | None = None) -> dict[str, str]:
    """供 AI 规划上下文：team 编号 → 职能。"""
    if config is None:
        return {str(tid): role for tid, role in TEAM_ROLE_DEFAULTS.items()}
    roles = resolve_all_team_roles(config)
    return {str(tid): role for tid, role in roles.items()}
