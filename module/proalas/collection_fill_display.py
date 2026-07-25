# -*- coding: utf-8 -*-
"""自动补齐图鉴 WebUI：从 ProalasData / 日历读取建造补齐与打捞补齐展示数据。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from module.config.deep import deep_get
from module.proalas.global_activity_calendar import get_global_quadrant, resolve_manifest_blue


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _ship_list(raw: Any) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for x in raw if isinstance(raw, (list, tuple)) else [raw]:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    return out


def _resolve_up_ships(config_data: dict[str, Any]) -> list[str]:
    cached = _ship_list(deep_get(config_data, ['ProalasData', 'GachaUp', 'upShips'], []))
    if cached:
        return cached
    server = str(deep_get(config_data, ['Alas', 'Emulator', 'PackageName'], 'cn') or 'cn')
    blue = get_global_quadrant(_today_str(), 'blue')
    gacha = blue.get('gacha') if isinstance(blue.get('gacha'), dict) else {}
    up = _ship_list(gacha.get('up_ships'))
    if up:
        return up
    manifest = resolve_manifest_blue(server)
    if manifest and isinstance(manifest.get('gacha'), dict):
        return _ship_list(manifest['gacha'].get('up_ships'))
    return []


def _resolve_farm_targets(config_data: dict[str, Any]) -> list[str]:
    stored = _ship_list(deep_get(config_data, ['ProalasData', 'CollectionFill', 'farm', 'targets'], []))
    if stored:
        return stored
    server = str(deep_get(config_data, ['Alas', 'Emulator', 'PackageName'], 'cn') or 'cn')
    blue = get_global_quadrant(_today_str(), 'blue')
    farm = _ship_list(blue.get('farm_ships'))
    if farm:
        return farm
    manifest = resolve_manifest_blue(server)
    if manifest:
        return _ship_list(manifest.get('farm_ships'))
    return []


def _gacha_status_label(
    *,
    up_ships: list[str],
    missing: list[str],
    uncertain: list[str],
    all_owned: bool | None,
    last_check: str,
) -> str:
    if not up_ships:
        return '未配置 UP 角色（等待活动同步写入 upShips）'
    if not last_check:
        return '尚未检测（请运行定时计划中的 UP 抽卡检测）'
    if uncertain:
        return f'部分未确定（{len(uncertain)} 艘需重检）'
    if all_owned is True or (not missing and up_ships):
        if not missing:
            return '全部已拥有'
    if missing:
        return f'缺 {len(missing)} 艘'
    return '已检测'


def _gacha_auto_status_text(config_data: dict[str, Any]) -> dict[str, str]:
    auto = deep_get(config_data, ['ProalasData', 'GachaAuto'], {}) or {}
    if not isinstance(auto, dict):
        auto = {}
    enabled = bool(deep_get(
        config_data,
        ['ProalasCollectionFill', 'ProalasCollectionFill', 'AutoGachaEnable'],
        False,
    ))
    today = str(auto.get('todayPulls') or '0')
    state = str(auto.get('lastState') or '—')
    reason = str(auto.get('lastReason') or '')
    last_at = str(auto.get('lastRunAt') or '—')
    if not enabled:
        label = '已关闭'
    elif state == 'done':
        label = f'今日已抽 {today}/20 发'
    elif state == 'skipped' and reason:
        label = f'未执行（{reason}）'
    elif state == 'error':
        label = f'异常（{reason or "—"}）'
    else:
        label = state if state != '—' else '等待执行'
    return {
        'autoLabel': label,
        'autoLastRun': last_at,
        'todayPulls': today,
    }


def build_gacha_card_view(config_data: dict[str, Any]) -> dict[str, Any]:
    """建造补齐卡片：未拥有 UP + 检测元信息。"""
    gacha_up = deep_get(config_data, ['ProalasData', 'GachaUp'], {}) or {}
    if not isinstance(gacha_up, dict):
        gacha_up = {}

    up_ships = _resolve_up_ships(config_data)
    results = gacha_up.get('results') if isinstance(gacha_up.get('results'), list) else []
    missing: list[str] = []
    uncertain: list[str] = []
    owned_names: list[str] = []

    result_by_ship = {
        str(r.get('ship', '')).strip(): r
        for r in results
        if isinstance(r, dict) and str(r.get('ship', '')).strip()
    }
    for name in up_ships:
        rep = result_by_ship.get(name)
        if not rep:
            if gacha_up.get('lastCheckAt'):
                uncertain.append(name)
            continue
        if rep.get('ok') and rep.get('owned') is False:
            missing.append(name)
        elif rep.get('ok') and rep.get('owned') is True:
            owned_names.append(name)
        else:
            uncertain.append(name)

    stored_missing = _ship_list(gacha_up.get('missing'))
    if stored_missing and not missing:
        missing = stored_missing

    last_check = str(gacha_up.get('lastCheckAt') or '').strip()
    all_owned = gacha_up.get('allOwned')
    if all_owned is None and up_ships and last_check and not missing and not uncertain:
        all_owned = True

    return {
        'upShips': up_ships,
        'missing': missing,
        'owned': owned_names,
        'uncertain': uncertain,
        'lastCheckAt': last_check or '—',
        'allOwned': all_owned,
        'statusLabel': _gacha_status_label(
            up_ships=up_ships,
            missing=missing,
            uncertain=uncertain,
            all_owned=all_owned if isinstance(all_owned, bool) else None,
            last_check=last_check,
        ),
        'missingText': '、'.join(missing) if missing else (
            '无（已全部拥有）' if up_ships and last_check and not uncertain else '—'
        ),
        'uncertainText': '、'.join(uncertain) if uncertain else '',
        **_gacha_auto_status_text(config_data),
    }


def build_farm_card_view(config_data: dict[str, Any]) -> dict[str, Any]:
    """打捞补齐卡片：未拥有打捞船 + 当前执行目标。"""
    farm = deep_get(config_data, ['ProalasData', 'CollectionFill', 'farm'], {}) or {}
    if not isinstance(farm, dict):
        farm = {}

    targets = _resolve_farm_targets(config_data)
    results = farm.get('results') if isinstance(farm.get('results'), list) else []
    missing: list[str] = []
    uncertain: list[str] = []

    result_by_ship = {
        str(r.get('ship', '')).strip(): r
        for r in results
        if isinstance(r, dict) and str(r.get('ship', '')).strip()
    }
    for name in targets:
        rep = result_by_ship.get(name)
        if not rep:
            missing.append(name)
            continue
        if rep.get('ok') and rep.get('owned') is False:
            missing.append(name)
        elif rep.get('ok') and rep.get('owned') is True:
            pass
        else:
            uncertain.append(name)

    stored_missing = _ship_list(farm.get('missing'))
    if stored_missing:
        missing = stored_missing

    active = str(farm.get('activeTarget') or farm.get('activeFarm') or '').strip()
    active_stage = str(farm.get('activeStage') or '').strip()
    updated = str(farm.get('updatedAt') or '').strip()

    if not targets:
        missing_text = '尚未配置打捞目标（日历 farm_ships 或 ProalasData.CollectionFill.farm.targets）'
        active_text = '未开始'
    elif not missing and not uncertain:
        missing_text = '无（已全部拥有）'
        active_text = '—' if not active else active
    else:
        missing_text = '、'.join(missing) if missing else '—'
        if uncertain and not missing:
            missing_text = f'{missing_text}（未确定：{"、".join(uncertain)}）'
        if active:
            active_text = f'{active} @ {active_stage}' if active_stage else active
        elif not missing:
            active_text = '—'
        else:
            active_text = '未开始'

    return {
        'targets': targets,
        'missing': missing,
        'uncertain': uncertain,
        'missingText': missing_text,
        'activeText': active_text,
        'updatedAt': updated or '—',
    }


def _research_incomplete_count(research: dict[str, Any], results: list[dict]) -> int | None:
    stored = research.get('incompleteCount')
    if isinstance(stored, int) and stored >= 0:
        return stored
    if not results:
        return None
    return sum(1 for r in results if isinstance(r, dict) and r.get('completed') is not True)


def _research_position_text(
    *,
    series: Any,
    index: Any,
    ship_name: str,
    has_snapshot: bool,
) -> str:
    series_n = None
    index_n = None
    try:
        if series is not None and str(series).strip() != '':
            series_n = int(series)
    except (TypeError, ValueError):
        series_n = None
    try:
        if index is not None and str(index).strip() != '':
            index_n = int(index)
    except (TypeError, ValueError):
        index_n = None

    if series_n and index_n:
        text = f'第{series_n}期 · 第{index_n}艘'
        if ship_name:
            return f'{text}（{ship_name}）'
        return text
    parts: list[str] = []
    if series_n:
        parts.append(f'第{series_n}期')
    if index_n:
        parts.append(f'第{index_n}艘')
    if parts:
        text = ' · '.join(parts)
        return f'{text}（{ship_name}）' if ship_name else text
    if ship_name:
        return ship_name
    return '未开始' if not has_snapshot else '—'


def _research_progress_text(*, stage: Any, phase: str, has_snapshot: bool) -> str:
    stage_text = ''
    if stage is not None and str(stage).strip() != '':
        stage_text = str(stage).strip()
        if stage_text.isdigit():
            stage_text = f'第{stage_text}阶段'

    phase = (phase or '').strip().upper()
    # 补齐科研扫描写入：RUNNING / END / START（旧版船坞命运：DEV / FATE）
    phase_map = {
        'RUNNING': '研究进行中',
        'END': '待完成研究',
        'START': '待开始研究',
        'DEV': '开发',
        'FATE': '命运',
    }
    if phase in phase_map:
        phase_cn = phase_map[phase]
        if stage_text:
            return f'{phase_cn} · {stage_text}'
        return phase_cn
    if stage_text:
        return stage_text
    return '未开始' if not has_snapshot else '—'


def _research_incomplete_labels(research: dict[str, Any], results: list[dict]) -> list[str]:
    stored = research.get('incompleteLabels')
    labels: list[str] = []
    if isinstance(stored, (list, tuple)):
        for x in stored:
            s = str(x).strip()
            if s and s not in labels:
                labels.append(s)
    if labels:
        return labels
    for r in results:
        if not isinstance(r, dict) or r.get('completed') is True:
            continue
        label = str(r.get('label') or '').strip()
        if not label:
            series = r.get('series')
            ship = str(r.get('ship') or '').strip()
            if series and ship:
                from module.CollectionFill.assets import incomplete_label
                label = incomplete_label(int(series), ship)
        if label and label not in labels:
            labels.append(label)
    return labels


def build_research_card_view(config_data: dict[str, Any]) -> dict[str, Any]:
    """科研补齐卡片：未完成数量、当前期数/序号、当前阶段。"""
    from module.proalas.collection_fill_policy import research_next_due_hint

    research = deep_get(config_data, ['ProalasData', 'CollectionFill', 'research'], {}) or {}
    if not isinstance(research, dict):
        research = {}

    results = [
        r for r in (research.get('results') or [])
        if isinstance(r, dict)
    ]
    incomplete_count = _research_incomplete_count(research, results)
    incomplete_labels = _research_incomplete_labels(research, results)

    series = research.get('currentSeries', research.get('activeSeries'))
    index = research.get('currentIndex', research.get('activeIndex'))
    stage = research.get('currentStage', research.get('activeStage'))
    ship_name = str(research.get('currentShip') or research.get('activeShip') or '').strip()
    phase = str(research.get('currentPhase') or research.get('activePhase') or '').strip()
    updated = str(
        research.get('lastScanAt')
        or research.get('updatedAt')
        or research.get('lastCheckAt')
        or ''
    ).strip()
    has_snapshot = bool(updated or results or incomplete_count is not None or incomplete_labels)
    due_text = research_next_due_hint(config_data)

    if incomplete_count is None and not has_snapshot:
        incomplete_text = '尚未检测（定时计划按周到期扫描）'
    elif incomplete_count is None:
        incomplete_text = '—'
    elif incomplete_count == 0:
        incomplete_text = '0（已全部完成）'
    elif incomplete_labels:
        preview = '、'.join(incomplete_labels[:6])
        more = f' 等{incomplete_count}艘' if incomplete_count > 6 else ''
        incomplete_text = f'{incomplete_count} 艘：{preview}{more}'
    else:
        incomplete_text = f'{incomplete_count} 艘'

    position_text = _research_position_text(
        series=series,
        index=index,
        ship_name=ship_name,
        has_snapshot=has_snapshot,
    )
    progress_text = _research_progress_text(
        stage=stage,
        phase=phase,
        has_snapshot=has_snapshot,
    )

    return {
        'incompleteCount': incomplete_count,
        'incompleteText': incomplete_text,
        'incompleteLabels': incomplete_labels,
        'positionText': position_text,
        'progressText': progress_text,
        'dueText': due_text,
        'updatedAt': updated or '—',
        'hasSnapshot': has_snapshot,
    }
