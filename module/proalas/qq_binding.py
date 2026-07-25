# -*- coding: utf-8 -*-
"""QQ 与 Alas 设备绑定（v1：1 QQ → 1 device）；供 WebUI 与后续 B111 Router 读取。"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from module.config.utils import read_file, write_file

BINDING_VERSION = 1
QQ_ID_RE = re.compile(r'^\d{5,12}$')
CHANGE_COOLDOWN_DAYS = 30


def binding_path() -> str:
    try:
        from mumucontrol.paths import migrate_legacy_runtime_files, qq_bindings_path

        migrate_legacy_runtime_files()
        return qq_bindings_path()
    except Exception:
        pass
    root = os.path.abspath('.')
    path = os.path.join(root, 'dap_data', 'qq_bindings.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def default_bindings() -> dict[str, Any]:
    return {
        'version': BINDING_VERSION,
        'bindings': {},
        'reverse': {},
    }


def load_bindings() -> dict[str, Any]:
    raw = read_file(binding_path())
    if not isinstance(raw, dict):
        return default_bindings()
    raw.setdefault('version', BINDING_VERSION)
    raw.setdefault('bindings', {})
    raw.setdefault('reverse', {})
    return raw


def save_bindings(data: dict[str, Any]) -> None:
    path = binding_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    data['version'] = BINDING_VERSION
    data['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    _rebuild_reverse(data)
    write_file(path, data)


def _rebuild_reverse(data: dict[str, Any]) -> None:
    reverse: dict[str, str] = {}
    bindings = data.get('bindings')
    if isinstance(bindings, dict):
        for device_id, row in bindings.items():
            if not isinstance(row, dict):
                continue
            qq = str(row.get('qq_id') or '').strip()
            if qq:
                reverse[qq] = str(device_id)
    data['reverse'] = reverse


def get_device_binding(device_id: str) -> dict[str, Any]:
    data = load_bindings()
    bindings = data.get('bindings') or {}
    row = bindings.get(device_id) if isinstance(bindings, dict) else None
    return dict(row) if isinstance(row, dict) else {}


def get_device_for_qq(qq_id: str) -> Optional[str]:
    data = load_bindings()
    reverse = data.get('reverse') or {}
    if isinstance(reverse, dict):
        dev = reverse.get(str(qq_id).strip())
        return str(dev) if dev else None
    return None


def _parse_updated_at(row: dict[str, Any]) -> Optional[datetime]:
    raw = row.get('updated_at') or row.get('bound_at') or ''
    if isinstance(raw, datetime):
        return raw.replace(microsecond=0)
    if isinstance(raw, str) and raw.strip():
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
            try:
                return datetime.strptime(raw.strip(), fmt)
            except ValueError:
                continue
    return None


def next_change_allowed_at(device_id: str) -> Optional[datetime]:
    row = get_device_binding(device_id)
    if not row:
        return None
    updated = _parse_updated_at(row)
    if not updated:
        return None
    return updated + timedelta(days=CHANGE_COOLDOWN_DAYS)


def can_change_binding(device_id: str, now: Optional[datetime] = None) -> tuple[bool, str]:
    now = now or datetime.now()
    row = get_device_binding(device_id)
    if not row or not row.get('qq_id'):
        return True, ''
    allowed = next_change_allowed_at(device_id)
    if allowed is None:
        return True, ''
    if now >= allowed:
        return True, ''
    return False, allowed.strftime('%Y-%m-%d %H:%M:%S')


def bind_qq(device_id: str, qq_id: str) -> tuple[bool, str]:
    qq = str(qq_id or '').strip()
    if not QQ_ID_RE.match(qq):
        return False, 'QQ 号须为 5～12 位数字'
    ok, allowed_at = can_change_binding(device_id)
    if not ok:
        return False, f'每月仅可更改一次，下次可改时间：{allowed_at}'

    data = load_bindings()
    bindings = data.setdefault('bindings', {})
    if not isinstance(bindings, dict):
        bindings = {}
        data['bindings'] = bindings

    reverse = data.get('reverse') or {}
    if isinstance(reverse, dict):
        old_device = reverse.get(qq)
        if old_device and old_device != device_id:
            return False, f'该 QQ 已绑定设备 {old_device}'

    prev = bindings.get(device_id) if isinstance(bindings.get(device_id), dict) else {}
    prev_qq = str(prev.get('qq_id') or '').strip()
    if prev_qq and prev_qq != qq:
        ok2, allowed_at2 = can_change_binding(device_id)
        if not ok2:
            return False, f'每月仅可更改一次，下次可改时间：{allowed_at2}'

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    bindings[device_id] = {
        'qq_id': qq,
        'bound_at': prev.get('bound_at') or now_str,
        'updated_at': now_str,
        'plan': str(prev.get('plan') or 'normal'),
    }
    save_bindings(data)
    return True, f'已绑定 QQ {qq}'


def get_qq_plan(qq_id: str) -> str:
    """套餐：normal（默认 50 条/天）| pro（500 条/天，含 pro_plus）。"""
    dev = get_device_for_qq(qq_id)
    if not dev:
        return 'normal'
    row = get_device_binding(dev)
    plan = str(row.get('plan') or 'normal').strip().lower()
    return 'pro' if plan in ('pro', 'pro_plus') else 'normal'


def sync_binding_plan_from_config(device_id: str, plan_type: str) -> None:
    """将 config ProalasAccount.PlanType 同步到 qq_bindings（Router 限频用）。"""
    plan = str(plan_type or 'normal').strip().lower()
    if plan not in ('normal', 'pro', 'pro_plus'):
        plan = 'normal'
    data = load_bindings()
    bindings = data.get('bindings')
    if not isinstance(bindings, dict):
        return
    row = bindings.get(device_id)
    if not isinstance(row, dict) or not str(row.get('qq_id') or '').strip():
        return
    if str(row.get('plan') or '') == plan:
        return
    row['plan'] = plan
    save_bindings(data)


def set_qq_plan(device_id: str, plan: str) -> tuple[bool, str]:
    plan = str(plan or 'normal').strip().lower()
    if plan not in ('normal', 'pro', 'pro_plus'):
        return False, 'plan 须为 normal、pro 或 pro_plus'
    data = load_bindings()
    bindings = data.get('bindings')
    if not isinstance(bindings, dict) or device_id not in bindings:
        return False, '设备未绑定 QQ'
    row = bindings[device_id]
    if not isinstance(row, dict):
        return False, '绑定数据异常'
    row['plan'] = plan
    save_bindings(data)
    return True, f'已设置 {device_id} 套餐为 {plan}'


def unbind_qq(device_id: str) -> tuple[bool, str]:
    ok, allowed_at = can_change_binding(device_id)
    if not ok:
        return False, f'每月仅可更改一次，下次可改时间：{allowed_at}'
    data = load_bindings()
    bindings = data.get('bindings')
    if not isinstance(bindings, dict) or device_id not in bindings:
        return False, '当前未绑定 QQ'
    bindings.pop(device_id, None)
    save_bindings(data)
    return True, '已解除 QQ 绑定'
