# -*- coding: utf-8 -*-
"""从 Alas 历史日志解析 oil / money / Rmb（非实时 OCR）。"""
from __future__ import annotations

import os
from typing import Optional

from module.logger import logger

DEFAULT_ALAS_LOG = os.environ.get('ALAS_LOG_PATH', './log')

# 日志 attr 键 -> snapshot 字段（写入 UserData 时再映射到 GameResource）
LOG_KEY_TO_SNAPSHOT = {
    'OCR_OIL': 'oil',
    'OCR_COIN': 'money',
    'SHOP_GEMS': 'rmb',
}


def _extract_log_tail(line: str, key: str) -> str:
    prefix = f'[{key}'
    idx = line.find(prefix)
    if idx < 0:
        return ''
    close = line.find(']', idx)
    if close < 0:
        return ''
    return line[close + 1 :].strip()


def _parse_log_value(key: str, tail: str) -> Optional[int]:
    if not tail:
        return None
    digits = ''.join(filter(str.isdigit, tail))
    if not digits:
        return None
    if key == 'Event_PT' and digits.endswith('300000'):
        digits = digits[:-6]
    try:
        return int(digits)
    except ValueError:
        return None


def _latest_value_in_file(log_path: str, key: str) -> Optional[int]:
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError as e:
        logger.debug('ProalasCollector log read failed %s: %s', log_path, e)
        return None
    prefix = f'[{key}'
    for line in reversed(lines):
        if prefix not in line:
            continue
        tail = _extract_log_tail(line, key)
        val = _parse_log_value(key, tail)
        if val is not None:
            return val
    return None


def _device_log_files(device_id: str, log_dir: str) -> list[str]:
    if not log_dir or not os.path.isdir(log_dir):
        return []
    suffix = f'_{device_id}.txt'
    files = []
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
    return [path for _, path in files]


def read_oil_coin_rmb_from_logs(
    device_id: str,
    log_dir: Optional[str] = None,
) -> dict[str, int]:
    """
    从该设备全部历史日志（``*_{device_id}.txt``）取各键最后一条记录。
    按文件修改时间从新到旧扫描，找到即停。
    """
    log_dir = (log_dir or DEFAULT_ALAS_LOG).strip() or DEFAULT_ALAS_LOG
    files = _device_log_files(device_id, log_dir)
    if not files:
        logger.warning(
            'ProalasCollector: no log files *_%s.txt under %s',
            device_id,
            os.path.abspath(log_dir),
        )
        return {}

    snapshot: dict[str, int] = {}
    for log_key, field in LOG_KEY_TO_SNAPSHOT.items():
        for log_file in reversed(files):
            val = _latest_value_in_file(log_file, log_key)
            if val is not None:
                snapshot[field] = val
                logger.info(
                    'ProalasCollector log %s=%s from %s',
                    field,
                    val,
                    os.path.basename(log_file),
                )
                break
        else:
            logger.info('ProalasCollector log: no %s in history logs', log_key)

    return snapshot


def read_boat_max_from_logs(
    config_name: str,
    log_dir: Optional[str] = None,
) -> int:
    """从 Alas 日志 BOAT_MAX 取船坞上限（退役任务写入）。"""
    log_dir = (log_dir or DEFAULT_ALAS_LOG).strip() or DEFAULT_ALAS_LOG
    files = _device_log_files(config_name, log_dir)
    for log_file in reversed(files):
        val = _latest_value_in_file(log_file, 'BOAT_MAX')
        if val is not None and val > 0:
            logger.info(
                'ProalasBoatMessage log BoatMax=%s from %s',
                val,
                os.path.basename(log_file),
            )
            return val
    return 0
