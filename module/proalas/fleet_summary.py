# -*- coding: utf-8 -*-
"""从 config ProalasData.FleetStrength 格式化编队展示文本 / HTML。"""
from __future__ import annotations

from html import escape

from module.config.deep import deep_get


def _team_entry(config_data: dict, team_id: int) -> dict | None:
    fs = deep_get(config_data, ['ProalasData', 'FleetStrength'], None)
    if not isinstance(fs, dict):
        return None
    teams = fs.get('teams') or []
    if not isinstance(teams, list):
        return None
    for entry in teams:
        if not isinstance(entry, dict):
            continue
        try:
            if int(entry.get('team', 0)) == team_id:
                return entry
        except (TypeError, ValueError):
            continue
    return None


def _ships_by_slot(entry: dict) -> dict[int, dict]:
    ships = entry.get('ships') or []
    out: dict[int, dict] = {}
    if not isinstance(ships, list):
        return out
    for ship in ships:
        if not isinstance(ship, dict):
            continue
        try:
            slot = int(ship.get('slot', 0))
        except (TypeError, ValueError):
            continue
        if slot:
            out[slot] = ship
    return out


def compute_row_powers(ships: list[dict]) -> tuple[int, int]:
    back = sum(
        int(s['power'])
        for s in ships
        if isinstance(s, dict) and 1 <= int(s.get('slot', 0)) <= 3 and s.get('power')
    )
    front = sum(
        int(s['power'])
        for s in ships
        if isinstance(s, dict) and 4 <= int(s.get('slot', 0)) <= 6 and s.get('power')
    )
    return back, front


def _format_ship_side_plain(label: str, ship: dict | None) -> str:
    if not ship or ship.get('empty'):
        return f'{label} — 战力—'
    name = str(ship.get('name') or '').strip() or '—'
    power = ship.get('power')
    try:
        ptxt = f'战力{int(power)}' if power else '战力—'
    except (TypeError, ValueError):
        ptxt = '战力—'
    return f'{label} {name} {ptxt}'


def _fmt_power(val) -> str:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return '—'
    return f'{n:,}'


def _ship_chip_html(ship: dict | None, *, slot_label: str) -> str:
    if not ship or ship.get('empty'):
        return (
            f'<div class="pa-afc-ship pa-afc-ship-empty" title="{escape(slot_label)}">'
            f'<span class="pa-afc-ship-slot">{escape(slot_label)}</span>'
            f'<span class="pa-afc-ship-name">空槽</span>'
            f'</div>'
        )
    name = escape(str(ship.get('name') or '').strip() or '—')
    power = _fmt_power(ship.get('power'))
    return (
        f'<div class="pa-afc-ship" title="{escape(slot_label)}">'
        f'<span class="pa-afc-ship-slot">{escape(slot_label)}</span>'
        f'<span class="pa-afc-ship-name">{name}</span>'
        f'<span class="pa-afc-ship-pwr">{power}</span>'
        f'</div>'
    )


def format_team_fleet_stats_html(config_data: dict, team_id: int) -> str:
    """队总战力摘要（HTML 片段）。"""
    entry = _team_entry(config_data, team_id)
    if not entry:
        return ''
    total = entry.get('totalPower')
    front = entry.get('frontPower')
    back = entry.get('backPower')
    parts: list[str] = []
    if total is not None:
        parts.append(f'总 {_fmt_power(total)}')
    if front is not None and back is not None:
        parts.append(f'前 {_fmt_power(front)} · 后 {_fmt_power(back)}')
    if not parts:
        return ''
    return f'<span class="pa-afc-stats">{" · ".join(parts)}</span>'


def format_team_fleet_html(config_data: dict, team_id: int) -> str:
    """六槽编队卡片：前排 / 后排分区展示。"""
    entry = _team_entry(config_data, team_id)
    if not entry:
        return (
            '<div class="pa-afc-empty-box">'
            '<div class="pa-afc-empty-icon">⚓</div>'
            '<p class="pa-afc-empty">暂无编队数据</p>'
            '<p class="pa-afc-empty-hint">请运行 <strong>ProAlas 采集 → 编队采集</strong> 后刷新本页</p>'
            '</div>'
        )

    by_slot = _ships_by_slot(entry)
    front_slots = [_ship_chip_html(by_slot.get(i + 3), slot_label=f'前{i}') for i in range(1, 4)]
    back_slots = [_ship_chip_html(by_slot.get(i), slot_label=f'后{i}') for i in range(1, 4)]
    return (
        '<div class="pa-afc-formation">'
        '<div class="pa-afc-row">'
        '<div class="pa-afc-row-head"><span class="pa-afc-row-tag pa-afc-tag-vanguard">先锋</span>'
        '<span class="pa-afc-row-sub">前排 · 槽 4–6</span></div>'
        f'<div class="pa-afc-ships">{"".join(front_slots)}</div>'
        '</div>'
        '<div class="pa-afc-row">'
        '<div class="pa-afc-row-head"><span class="pa-afc-row-tag pa-afc-tag-main">主力</span>'
        '<span class="pa-afc-row-sub">后排 · 槽 1–3</span></div>'
        f'<div class="pa-afc-ships">{"".join(back_slots)}</div>'
        '</div>'
        '</div>'
    )


def format_team_summary(config_data: dict, team_id: int) -> str:
    entry = _team_entry(config_data, team_id)
    if not entry:
        return f'第 {team_id} 队：暂无编队数据（请先在 ProAlas 采集 → 编队采集 运行一次）'

    by_slot = _ships_by_slot(entry)
    lines: list[str] = []
    for i in range(1, 4):
        left = _format_ship_side_plain(f'前排{i}', by_slot.get(i + 3))
        right = _format_ship_side_plain(f'后排{i}', by_slot.get(i))
        lines.append(f'{left}    {right}')
    return f'第 {team_id} 队\n' + '\n'.join(lines)


def all_teams_summary(config_data: dict) -> list[str]:
    return [format_team_summary(config_data, i) for i in range(1, 7)]
