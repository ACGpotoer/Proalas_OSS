# -*- coding: utf-8 -*-
"""
DAP 临时远控（py-scrcpy via mmc-agent）：
- 短期 ticket（HMAC 签名 + 登录 session 绑定）
- 按套餐每日配额：Normal 10 分钟 / Pro·Pro+ 2 小时
- 单次时长：Normal ≤10 分钟 / Pro ≤60 分钟（且不超过当日剩余）
- 启动时暂停 Alas（mmc pause）
- 画面/触控经 /app/pro/remote/{frame,touch,text,key} 转发到 mmc
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
# ticket -> meta
_TICKETS: dict[str, dict[str, Any]] = {}
# 同设备并发 start 防护（准备约 1 分钟，防重复点击顶掉会话）
_STARTING_DEVICES: set[str] = set()

# Normal：日 10 分钟、单次 10 分钟；Pro/Pro+：日 2 小时、单次最多 60 分钟
_DEFAULT_QUOTA = {
    'normal': {'daily': 600, 'session': 600},
    'pro': {'daily': 7200, 'session': 3600},
    'pro_plus': {'daily': 7200, 'session': 3600},
}


def _cfg_get(config: dict[str, Any], key: str, default: Any) -> Any:
    if key in config and config.get(key) not in (None, ''):
        return config.get(key)
    return os.environ.get(key, default)


def _int_cfg(config: dict[str, Any], key: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(_cfg_get(config, key, default)), hi))
    except (TypeError, ValueError):
        return default


def normalize_plan_type(plan: str) -> str:
    p = str(plan or 'normal').strip().lower().replace('+', '_plus')
    if p in ('pro_plus', 'proplus'):
        return 'pro_plus'
    if p == 'pro':
        return 'pro'
    return 'normal'


def device_plan_type(config: dict[str, Any], device_id: str) -> str:
    from proalas.alas_config import load_device_config, read_account_block

    cfg_dir = str(config.get('CONFIG_DIR') or '').strip()
    if not cfg_dir:
        return 'normal'
    try:
        device_cfg = load_device_config(cfg_dir, device_id)
        return normalize_plan_type(read_account_block(device_cfg).get('PlanType'))
    except Exception:
        logger.warning('resolve plan failed device=%s', device_id, exc_info=True)
        return 'normal'


def plan_label(plan: str) -> str:
    return {'normal': 'Normal', 'pro': 'Pro', 'pro_plus': 'Pro+'}.get(
        normalize_plan_type(plan), 'Normal'
    )


def daily_quota_sec(config: dict[str, Any], device_id: str = '', plan: str = '') -> int:
    """按套餐返回日配额（秒）。可传 plan 或 device_id。"""
    p = normalize_plan_type(plan) if plan else (
        device_plan_type(config, device_id) if device_id else 'normal'
    )
    if p in ('pro', 'pro_plus'):
        return _int_cfg(
            config, 'REMOTE_DAILY_QUOTA_PRO_SEC',
            _DEFAULT_QUOTA['pro']['daily'], lo=60, hi=86400,
        )
    if _cfg_get(config, 'REMOTE_DAILY_QUOTA_NORMAL_SEC', None) not in (None, ''):
        return _int_cfg(
            config, 'REMOTE_DAILY_QUOTA_NORMAL_SEC',
            _DEFAULT_QUOTA['normal']['daily'], lo=60, hi=86400,
        )
    legacy = _cfg_get(config, 'REMOTE_DAILY_QUOTA_SEC', None)
    if legacy not in (None, ''):
        return _int_cfg(config, 'REMOTE_DAILY_QUOTA_SEC', 600, lo=60, hi=86400)
    return _DEFAULT_QUOTA['normal']['daily']


def session_ttl_sec(config: dict[str, Any], device_id: str = '', plan: str = '') -> int:
    """单次会话上限（秒）。"""
    p = normalize_plan_type(plan) if plan else (
        device_plan_type(config, device_id) if device_id else 'normal'
    )
    if p in ('pro', 'pro_plus'):
        return _int_cfg(
            config, 'REMOTE_SESSION_TTL_PRO_SEC',
            _DEFAULT_QUOTA['pro']['session'], lo=60, hi=7200,
        )
    if _cfg_get(config, 'REMOTE_SESSION_TTL_NORMAL_SEC', None) not in (None, ''):
        return _int_cfg(
            config, 'REMOTE_SESSION_TTL_NORMAL_SEC',
            _DEFAULT_QUOTA['normal']['session'], lo=60, hi=3600,
        )
    legacy = _cfg_get(config, 'REMOTE_SESSION_TTL_SEC', None)
    if legacy not in (None, ''):
        return _int_cfg(config, 'REMOTE_SESSION_TTL_SEC', 600, lo=60, hi=3600)
    return _DEFAULT_QUOTA['normal']['session']


def _secret_key(config: dict[str, Any]) -> str:
    return str(
        config.get('SECRET_KEY')
        or _cfg_get(config, 'FLASK_SECRET_KEY', 'dev-secret-change-me')
    )


def ensure_session_bind(flask_session: Any) -> str:
    """登录会话绑定令牌：换浏览器/重新登录后旧 ticket 失效。"""
    token = str(flask_session.get('_remote_bind') or '').strip()
    if not token:
        token = secrets.token_urlsafe(24)
        flask_session['_remote_bind'] = token
    return token


def mint_ticket(config: dict[str, Any], device_id: str, bind: str) -> str:
    """opaque.nonce + HMAC，需与服务端 _TICKETS 同时存在才有效。"""
    device_id = str(device_id).upper().strip()
    bind = str(bind or '').strip()
    nonce = secrets.token_urlsafe(24)
    msg = f'{nonce}|{device_id}|{bind}'.encode('utf-8')
    sig = hmac.new(_secret_key(config).encode('utf-8'), msg, hashlib.sha256).hexdigest()[:32]
    return f'{nonce}.{sig}'


def verify_ticket_mac(
    config: dict[str, Any], ticket: str, device_id: str, bind: str,
) -> bool:
    ticket = str(ticket or '').strip()
    device_id = str(device_id).upper().strip()
    bind = str(bind or '').strip()
    if not ticket or not device_id or not bind or '.' not in ticket:
        return False
    nonce, _, sig = ticket.partition('.')
    if not nonce or not sig:
        return False
    msg = f'{nonce}|{device_id}|{bind}'.encode('utf-8')
    expect = hmac.new(_secret_key(config).encode('utf-8'), msg, hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expect)


def _quota_path(config: dict[str, Any]) -> str:
    root = (config.get('CONFIG_DIR') or '').strip()
    if not root:
        root = os.path.join('.', 'config')
    parent = os.path.dirname(os.path.abspath(root))
    runtime = os.path.join(parent, 'mumucontrol', 'runtime')
    os.makedirs(runtime, exist_ok=True)
    return os.path.join(runtime, 'RemoteQuota.json')


def _load_quota(config: dict[str, Any]) -> dict[str, Any]:
    path = _quota_path(config)
    if not os.path.isfile(path):
        return {'version': 1, 'devices': {}}
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {'version': 1, 'devices': {}}
    except (OSError, json.JSONDecodeError):
        return {'version': 1, 'devices': {}}


def _save_quota(config: dict[str, Any], data: dict[str, Any]) -> None:
    path = _quota_path(config)
    data['updatedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    fd, tmp = tempfile.mkstemp(suffix='.json', prefix='.rq.', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def quota_status(config: dict[str, Any], device_id: str) -> dict[str, Any]:
    device_id = str(device_id).upper().strip()
    day = datetime.now().strftime('%Y-%m-%d')
    plan = device_plan_type(config, device_id)
    data = _load_quota(config)
    devices = data.setdefault('devices', {})
    row = devices.get(device_id) if isinstance(devices, dict) else None
    if not isinstance(row, dict) or str(row.get('day') or '') != day:
        used = 0
    else:
        used = max(0, int(row.get('used_sec') or 0))
    limit = daily_quota_sec(config, device_id=device_id, plan=plan)
    left = max(0, limit - used)
    is_pro = plan in ('pro', 'pro_plus')
    return {
        'day': day,
        'used_sec': used,
        'limit_sec': limit,
        'remaining_sec': left,
        'plan': plan,
        'plan_label': plan_label(plan),
        'session_ttl_sec': session_ttl_sec(config, device_id=device_id, plan=plan),
        'limit_minutes': limit // 60,
        'remaining_minutes': left // 60,
        'is_pro': is_pro,
        'hint': (
            f'当前 {plan_label(plan)}：今日远控限额 {limit // 60} 分钟'
            + (
                '；升级 Pro 后每日可 2 小时'
                if not is_pro
                else '（单次最长 60 分钟）'
            )
        ),
    }


def _consume_quota(config: dict[str, Any], device_id: str, seconds: int) -> None:
    device_id = str(device_id).upper().strip()
    seconds = max(0, int(seconds))
    if seconds <= 0:
        return
    day = datetime.now().strftime('%Y-%m-%d')
    data = _load_quota(config)
    devices = data.setdefault('devices', {})
    row = devices.get(device_id)
    if not isinstance(row, dict) or str(row.get('day') or '') != day:
        row = {'day': day, 'used_sec': 0}
    row['used_sec'] = max(0, int(row.get('used_sec') or 0)) + seconds
    row['day'] = day
    devices[device_id] = row
    _save_quota(config, data)


def _mmc_root(config: dict[str, Any]) -> str:
    """MMC_COMMAND_URL 可能是 host、或带 /mmc/command；统一成 http://host:port。"""
    url = (config.get('MMC_COMMAND_URL') or '').strip().rstrip('/')
    if not url:
        return ''
    for suffix in ('/mmc/command', '/mmc'):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def _mmc_post(
    config: dict[str, Any],
    path: str,
    body: dict[str, Any],
    *,
    timeout: float = 90.0,
) -> tuple[bool, dict[str, Any], str]:
    root = _mmc_root(config)
    token = (config.get('MMC_COMMAND_TOKEN') or '').strip()
    if not root:
        return False, {}, '未配置 MMC_COMMAND_URL'
    path = path if path.startswith('/') else f'/{path}'
    endpoint = f'{root}{path}'
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        resp = httpx.post(
            endpoint, json=body, headers=headers, timeout=float(timeout), trust_env=False,
        )
        raw = (resp.text or '').strip()
        data: dict[str, Any] = {}
        if raw:
            try:
                parsed = resp.json()
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                preview = raw[:300].replace('\n', ' ')
                return False, {}, (
                    f'mmc 返回非 JSON (HTTP {resp.status_code}) '
                    f'url={endpoint} body={preview!r}。'
                    '请确认客户机已重启 host_agent/command_server，且含 /mmc/remote/start。'
                )
        if resp.status_code >= 400 or not data.get('ok'):
            err = str(
                data.get('error')
                or data.get('message')
                or (raw[:300] if raw else f'HTTP {resp.status_code}')
                or 'mmc error'
            )
            return False, data, err
        return True, data, str(data.get('message') or 'ok')
    except httpx.ConnectError as e:
        logger.warning('mmc remote unreachable: %s', e)
        return False, {}, '远控服务连不上（mmc-agent）'
    except Exception as e:
        logger.exception('mmc remote call failed')
        return False, {}, str(e)


def mmc_get_bytes(config: dict[str, Any], path: str) -> tuple[bool, bytes, str]:
    root = _mmc_root(config)
    token = (config.get('MMC_COMMAND_TOKEN') or '').strip()
    if not root:
        return False, b'', '未配置 MMC_COMMAND_URL'
    path = path if path.startswith('/') else f'/{path}'
    endpoint = f'{root}{path}'
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        resp = httpx.get(endpoint, headers=headers, timeout=30.0, trust_env=False)
        if resp.status_code >= 400:
            return False, b'', (resp.text or f'HTTP {resp.status_code}')[:200]
        return True, resp.content, ''
    except Exception as e:
        return False, b'', str(e)


def mmc_post_json(config: dict[str, Any], path: str, body: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
    return _mmc_post(config, path, body)


def lookup_ticket(ticket: str) -> Optional[dict[str, Any]]:
    ticket = str(ticket or '').strip()
    if not ticket:
        return None
    with _LOCK:
        meta = _TICKETS.get(ticket)
        if not meta:
            return None
        if datetime.now() >= meta['expires_at']:
            _TICKETS.pop(ticket, None)
            return None
        return dict(meta)


def validate_ticket_access(
    config: dict[str, Any],
    ticket: str,
    device_id: str,
    bind: str,
) -> Optional[dict[str, Any]]:
    """校验：服务端登记 + 设备一致 + session 绑定 + HMAC。"""
    device_id = str(device_id or '').upper().strip()
    bind = str(bind or '').strip()
    meta = lookup_ticket(ticket)
    if not meta or meta.get('device_id') != device_id:
        return None
    if str(meta.get('bind') or '') != bind:
        return None
    if not verify_ticket_mac(config, ticket, device_id, bind):
        return None
    return meta


def active_ticket_for_device(device_id: str) -> Optional[str]:
    """当前设备是否有未过期远控 ticket（供遗留反代）。"""
    device_id = str(device_id or '').upper().strip()
    if not device_id:
        return None
    with _LOCK:
        chosen = None
        chosen_at = None
        for ticket, meta in _TICKETS.items():
            if meta.get('device_id') != device_id:
                continue
            exp = meta.get('expires_at')
            if not exp or datetime.now() >= exp:
                continue
            started = meta.get('started_at') or exp
            if chosen is None or (chosen_at is None) or (started > chosen_at):
                chosen = ticket
                chosen_at = started
        return chosen


def purge_ticket(ticket: str) -> None:
    with _LOCK:
        _TICKETS.pop(str(ticket or '').strip(), None)


def _purge_device_tickets(device_id: str) -> None:
    device_id = str(device_id).upper().strip()
    with _LOCK:
        dead = [t for t, m in _TICKETS.items() if m.get('device_id') == device_id]
        for t in dead:
            _TICKETS.pop(t, None)


def start_remote(
    config: dict[str, Any],
    device_id: str,
    *,
    session_bind: str = '',
) -> tuple[bool, dict[str, Any]]:
    """
    签发 ticket → mmc 准备模拟器（停 Alas、保活/拉起 MuMu）→ 启 py-scrcpy。
    若本设备已有未过期远控，直接复用，避免二次 start 顶掉旧标签页。
    """
    # 开源阉割：无 MMC 则直接拒绝，避免无意义报错刷屏
    oss = os.environ.get('PROALAS_OSS', '1').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )
    if oss and not (config.get('MMC_COMMAND_URL') or '').strip():
        return False, {
            'ok': False,
            'error': '开源版未接入 mmc 远控（已剔除）',
        }

    device_id = str(device_id).upper().strip()
    bind = str(session_bind or '').strip()
    if not bind:
        return False, {'ok': False, 'error': '缺少登录会话绑定，请重新登录后再试'}

    q = quota_status(config, device_id)
    if q['remaining_sec'] < 60:
        return False, {
            'ok': False,
            'error': (
                f'今日远控配额已用尽'
                f'（{q["plan_label"]} 日限 {q["limit_sec"] // 60} 分钟）'
            ),
            'quota': q,
        }

    with _LOCK:
        if device_id in _STARTING_DEVICES:
            return False, {
                'ok': False,
                'error': '该设备正在准备远控（约1分钟），请勿重复点击',
                'quota': q,
            }
        # 复用未过期会话
        for ticket, meta in _TICKETS.items():
            if meta.get('device_id') != device_id:
                continue
            exp = meta.get('expires_at')
            if not exp or datetime.now() >= exp:
                continue
            left = int((exp - datetime.now()).total_seconds())
            if left < 30:
                continue
            view_path = f'/app/pro/remote/view?ticket={ticket}'
            return True, {
                'ok': True,
                'reused': True,
                'ticket': ticket,
                'device': device_id,
                'expires_at': exp.strftime('%Y-%m-%d %H:%M:%S'),
                'ttl_sec': left,
                'view_url': view_path,
                'quota': q,
                'message': f'远控进行中，已重新打开（剩余约 {left // 60} 分 {left % 60} 秒）',
            }
        _STARTING_DEVICES.add(device_id)

    try:
        ttl = min(
            session_ttl_sec(config, device_id=device_id, plan=q['plan']),
            int(q['remaining_sec']),
        )
        ticket = mint_ticket(config, device_id, bind)
        expires_at = datetime.now() + timedelta(seconds=ttl)

        ok, mmc, err = _mmc_post(
            config,
            '/mmc/remote/start',
            {
                'device': device_id,
                'ticket': ticket,
                'ttl_sec': ttl,
                'source': 'dap',
                'prepare_wait_sec': 60,
            },
            timeout=150.0,
        )
        if not ok:
            return False, {'ok': False, 'error': err, 'quota': q}

        with _LOCK:
            # 清掉同设备旧 ticket（mmc 侧已 replace）
            dead = [t for t, m in _TICKETS.items() if m.get('device_id') == device_id]
            for t in dead:
                _TICKETS.pop(t, None)
            _TICKETS[ticket] = {
                'ticket': ticket,
                'device_id': device_id,
                'bind': bind,
                'expires_at': expires_at,
                'ttl_sec': ttl,
                'plan': q['plan'],
                'local_http': str(mmc.get('local_http') or ''),
                'local_ws': str(mmc.get('local_ws') or ''),
                'port': int(mmc.get('port') or 0),
                'serial': str(mmc.get('serial') or ''),
                'started_at': datetime.now(),
                'quota_charged': False,
            }

        view_path = f'/app/pro/remote/view?ticket={ticket}'
        return True, {
            'ok': True,
            'ticket': ticket,
            'device': device_id,
            'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
            'ttl_sec': ttl,
            'view_url': view_path,
            'quota': quota_status(config, device_id),
            'prepare': mmc.get('prepare'),
            'message': (
                f'远控已开启，约 {ttl // 60} 分钟'
                f'（{q["plan_label"]}，今日剩余约 {q["remaining_sec"] // 60} 分钟）'
            ),
        }
    finally:
        with _LOCK:
            _STARTING_DEVICES.discard(device_id)


def stop_remote(config: dict[str, Any], device_id: str, ticket: str = '') -> tuple[bool, dict[str, Any]]:
    device_id = str(device_id).upper().strip()
    ticket = str(ticket or '').strip()
    meta = None
    if ticket:
        meta = lookup_ticket(ticket)
    # 结算配额：按实际已用秒数
    if meta and not meta.get('quota_charged'):
        used = int((datetime.now() - meta['started_at']).total_seconds())
        used = max(1, min(used, int(meta.get('ttl_sec') or used)))
        _consume_quota(config, device_id, used)
        with _LOCK:
            if ticket in _TICKETS:
                _TICKETS[ticket]['quota_charged'] = True
        purge_ticket(ticket)

    ok, mmc, err = _mmc_post(
        config,
        '/mmc/remote/stop',
        {'device': device_id, 'reason': 'dap_stop'},
    )
    if not ok:
        return False, {'ok': False, 'error': err, 'quota': quota_status(config, device_id)}
    return True, {
        'ok': True,
        'message': str(mmc.get('message') or '已结束远控'),
        'quota': quota_status(config, device_id),
    }


def remote_status_payload(config: dict[str, Any], device_id: str) -> dict[str, Any]:
    device_id = str(device_id).upper().strip()
    q = quota_status(config, device_id)
    active = None
    with _LOCK:
        for meta in _TICKETS.values():
            if meta.get('device_id') == device_id and datetime.now() < meta['expires_at']:
                active = {
                    'ticket_prefix': str(meta['ticket'])[:8],
                    'expires_at': meta['expires_at'].strftime('%Y-%m-%d %H:%M:%S'),
                    'remaining_sec': max(
                        0,
                        int((meta['expires_at'] - datetime.now()).total_seconds()),
                    ),
                    'view_url': f"/app/pro/remote/view?ticket={meta['ticket']}",
                }
                break
    return {
        'ok': True,
        'device': device_id,
        'active': active,
        'quota': q,
        'session_ttl_sec': q['session_ttl_sec'],
        'daily_quota_sec': q['limit_sec'],
        'plan': q['plan'],
        'plan_label': q['plan_label'],
    }
