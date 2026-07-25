# -*- coding: utf-8 -*-
"""ProalasData.ResourceHistory：按日归档资源时序（默认保留 30 天）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

from module.config.deep import deep_get, deep_set
from module.logger import logger

if TYPE_CHECKING:
    from module.config.config import AzurLaneConfig

RESOURCE_HISTORY_PATH = ('ProalasData', 'ResourceHistory')
DEFAULT_RETENTION_DAYS = 30

# snapshot / GameResource 字段 → ResourceHistory 序列名
HISTORY_KEYS = (
    'oil',
    'money',
    'cube',
    'act_pt',
    'rmb',
    'boat_rate',
    'boat_max',
)

_SKIP_ZERO_KEYS = frozenset({'oil', 'money', 'rmb'})


def _default_resource_history() -> dict[str, Any]:
    return {
        'retentionDays': DEFAULT_RETENTION_DAYS,
        'updatedAt': '',
        **{k: [] for k in HISTORY_KEYS},
    }


def _today() -> str:
    return date.today().isoformat()


def _cutoff_day(retention_days: int) -> str:
    days = max(1, int(retention_days or DEFAULT_RETENTION_DAYS))
    return (date.today() - timedelta(days=days - 1)).isoformat()


def _coerce_history_value(key: str, raw: Any) -> int | float | None:
    if raw is None:
        return None
    if key in _SKIP_ZERO_KEYS:
        try:
            val = int(raw)
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None
    if key == 'boat_rate':
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None
    if key == 'boat_max':
        try:
            val = int(raw)
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None
    try:
        if isinstance(raw, float):
            return raw
        return int(raw)
    except (TypeError, ValueError):
        return None


def _upsert_daily(series: list[dict[str, Any]], day: str, value: int | float) -> None:
    for i, pt in enumerate(series):
        if not isinstance(pt, dict):
            continue
        if str(pt.get('d') or '') == day:
            series[i] = {'d': day, 'v': value}
            return
    series.append({'d': day, 'v': value})
    series.sort(key=lambda x: str(x.get('d') or ''))


def _trim_series(series: list[dict[str, Any]], cutoff: str) -> list[dict[str, Any]]:
    out = [
        pt for pt in series
        if isinstance(pt, dict) and str(pt.get('d') or '') >= cutoff
    ]
    out.sort(key=lambda x: str(x.get('d') or ''))
    return out


def merge_resource_history(
    history: dict[str, Any] | None,
    patch: dict[str, Any],
    *,
    day: str | None = None,
) -> dict[str, Any]:
    """合并当日采样点，并裁剪到 retentionDays。"""
    if not isinstance(history, dict):
        history = _default_resource_history()
    retention = int(history.get('retentionDays') or DEFAULT_RETENTION_DAYS)
    cutoff = _cutoff_day(retention)
    day = day or _today()

    for key in HISTORY_KEYS:
        if key not in patch:
            continue
        val = _coerce_history_value(key, patch[key])
        if val is None:
            continue
        series = history.get(key)
        if not isinstance(series, list):
            series = []
        _upsert_daily(series, day, val)
        history[key] = _trim_series(series, cutoff)

    history['retentionDays'] = retention
    history['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    return history


def history_to_chart_series(history: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """转为折线图序列 { key: [ {t, v}, ... ] }。"""
    if not isinstance(history, dict):
        history = {}
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in HISTORY_KEYS}
    for key in HISTORY_KEYS:
        raw = history.get(key) or []
        if not isinstance(raw, list):
            continue
        for pt in raw:
            if not isinstance(pt, dict):
                continue
            d = str(pt.get('d') or '').strip()
            v = pt.get('v')
            if not d or v is None:
                continue
            out[key].append({'t': d, 'v': v})
    return out


def has_chart_data(series: dict[str, list[dict[str, Any]]]) -> bool:
    return any(series.get(k) for k in HISTORY_KEYS)


def append_resource_history_to_data(
    data: dict,
    patch: dict[str, Any],
    *,
    day: str | None = None,
) -> None:
    if not patch:
        return
    hist = deep_get(data, list(RESOURCE_HISTORY_PATH), None)
    hist = merge_resource_history(hist, patch, day=day)
    deep_set(data, list(RESOURCE_HISTORY_PATH), hist)
    logger.info(
        'ProalasData ResourceHistory updated keys=%s day=%s',
        sorted(k for k in HISTORY_KEYS if k in patch),
        day or _today(),
    )
