# -*- coding: utf-8 -*-
"""从 Alas 历史日志构建资源时序（供资源统计折线图）。"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Optional

from module.logger import logger

DEFAULT_ALAS_LOG = os.environ.get('ALAS_LOG_PATH', './log')

# 日志 attr → 序列键（与 UserData / 迁移文档字段对齐）
LOG_ATTR_TO_KEY = {
    'OCR_OIL': 'oil',
    'OCR_COIN': 'money',
    'SHOP_GEMS': 'rmb',
    'Event_PT': 'act_pt',
    'BUILD_CUBE_COUNT': 'cube',
    'BOAT_RATE': 'boat_rate',
    'BOAT_MAX': 'boat_max',
}

LINE_RE = re.compile(
    r'(\d{2}:\d{2}:\d{2})\.\d+.*?'
    r'\[(?P<key>[A-Z_0-9]+)(?:\s[\d.]+s)?\]\s*(?P<tail>[^\n\r]*)'
)


def _extract_log_tail(line: str, key: str) -> str:
    prefix = f'[{key}'
    idx = line.find(prefix)
    if idx < 0:
        return ''
    close = line.find(']', idx)
    if close < 0:
        return ''
    return line[close + 1 :].strip()


def _parse_value(key: str, tail: str) -> Optional[float]:
    if not tail:
        return None
    if key == 'BOAT_RATE':
        try:
            return float(tail.split()[0])
        except (ValueError, IndexError):
            return None
    digits = ''.join(c for c in tail if c.isdigit() or c == '.')
    if not digits:
        return None
    if key == 'Event_PT' and digits.endswith('300000'):
        digits = digits[:-6]
    try:
        if '.' in digits:
            return float(digits)
        return float(int(digits))
    except ValueError:
        return None


def _date_from_log_name(name: str) -> str:
    m = re.match(r'(\d{4}-\d{2}-\d{2})_', name)
    return m.group(1) if m else datetime.now().strftime('%Y-%m-%d')


def _device_log_files(device_id: str, log_dir: str) -> list[str]:
    if not log_dir or not os.path.isdir(log_dir):
        return []
    suffix = f'_{device_id}.txt'
    files: list[tuple[float, str]] = []
    for name in os.listdir(log_dir):
        if not name.endswith(suffix):
            continue
        full = os.path.join(log_dir, name)
        if os.path.isfile(full):
            try:
                files.append((os.path.getmtime(full), full))
            except OSError:
                pass
    files.sort(key=lambda x: x[0])
    return [p for _, p in files]


def build_resource_series(
    device_id: str,
    log_dir: Optional[str] = None,
    *,
    max_points_per_key: int = 240,
) -> dict[str, list[dict[str, Any]]]:
    """
    返回 { resource_key: [ { "t": date str, "v": number }, ... ] }
    优先 ProalasData.ResourceHistory；无数据时回退解析 Alas 日志。
    """
    from module.proalas.resource_history_store import has_chart_data, history_to_chart_series
    from module.proalas_collector.userdata import read_resource_history

    hist = read_resource_history(device_id)
    series = history_to_chart_series(hist)
    if has_chart_data(series):
        return series

    log_dir = (log_dir or DEFAULT_ALAS_LOG).strip() or DEFAULT_ALAS_LOG
    series = {k: [] for k in LOG_ATTR_TO_KEY.values()}

    for log_path in _device_log_files(device_id, log_dir):
        day = _date_from_log_name(os.path.basename(log_path))
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except OSError as e:
            logger.debug('resource_history read fail %s: %s', log_path, e)
            continue

        for line in lines:
            for log_key, res_key in LOG_ATTR_TO_KEY.items():
                if f'[{log_key}' not in line:
                    continue
                m = LINE_RE.search(line)
                if m and m.group('key') != log_key:
                    continue
                tail = _extract_log_tail(line, log_key)
                val = _parse_value(log_key, tail)
                if val is None:
                    continue
                tm = m.group(1) if m else '00:00:00'
                series[res_key].append({'t': f'{day} {tm}', 'v': val})
                break

    for key, points in series.items():
        if len(points) > max_points_per_key:
            step = max(1, len(points) // max_points_per_key)
            series[key] = points[::step][-max_points_per_key:]
    return series


def read_latest_boat_rate_from_logs(
    config_name: str,
    log_dir: Optional[str] = None,
) -> float:
    """日志中最近一次 BOAT_RATE（比例 0~1）。"""
    pts = build_resource_series(config_name, log_dir).get('boat_rate') or []
    if not pts:
        return 0.0
    try:
        return float(pts[-1]['v'])
    except (KeyError, TypeError, ValueError):
        return 0.0


def chart_series_percent(series: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """收藏率折线图用百分比刻度（0.802 → 80.2）。"""
    out = {k: list(v) for k, v in series.items()}
    pts = out.get('boat_rate') or []
    out['boat_rate'] = [
        {'t': p['t'], 'v': round(float(p['v']) * 100, 2)}
        for p in pts
        if p.get('v') is not None
    ]
    return out


def current_snapshot_from_userdata(
    config_name: str,
    user_data_path: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> dict[str, Any]:
    """从 ProalasData 读快照；收藏率缺失时回退到日志最新 BOAT_RATE。"""
    _ = user_data_path
    from module.proalas_collector.userdata import read_game_resource

    gr = read_game_resource(config_name)
    boat_rate = gr.get('BoatRate', 0) or 0
    try:
        boat_rate = float(boat_rate)
    except (TypeError, ValueError):
        boat_rate = 0.0
    if boat_rate <= 0:
        boat_rate = read_latest_boat_rate_from_logs(config_name, log_dir)

    return {
        'oil': gr.get('oil', 0),
        'money': gr.get('money', 0),
        'rmb': gr.get('Rmb', 0),
        'act_pt': gr.get('Act-Pt', 0),
        'cube': gr.get('cube', 0),
        'boat_rate': boat_rate,
        'boat_max': gr.get('BoatMax', 0),
        'boat_dock': gr.get('BoatDock', ''),
        'synced_at': gr.get('syncedAt') or '',
    }
