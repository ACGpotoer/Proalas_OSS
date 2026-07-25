"""HostAgent 专用：经 WebUI ProcessManager 启停 Alas 实例（与侧栏状态一致）。"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from module.logger import logger
from module.submodule.utils import get_config_mod
from module.webui.process_manager import ProcessManager
from module.webui.updater import updater

_ALAS_ROOT = Path(__file__).resolve().parents[2]
_HOST_AGENT_YAML = _ALAS_ROOT / 'mumucontrol' / 'host_agent.yaml'
_DEVICE_ID_RE = re.compile(r'^[0-9A-Z]{2}\d{3,}$', re.I)
_token_cache: str | None = None
_token_mtime: float = 0.0


def _load_expected_token() -> str:
    global _token_cache, _token_mtime
    env = (os.environ.get('MMC_COMMAND_TOKEN') or '').strip()
    if env:
        return env
    if not _HOST_AGENT_YAML.is_file():
        return ''
    try:
        mtime = _HOST_AGENT_YAML.stat().st_mtime
    except OSError:
        return _token_cache or ''
    if mtime == _token_mtime and _token_cache is not None:
        return _token_cache
    try:
        raw = yaml.safe_load(_HOST_AGENT_YAML.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError):
        return ''
    token = ''
    if isinstance(raw, dict):
        token = str(raw.get('command_server_token') or '').strip()
    _token_cache = token
    _token_mtime = mtime
    return token


def _auth_ok(request: Request) -> bool:
    token = _load_expected_token()
    if not token:
        return False
    auth = request.headers.get('authorization') or ''
    if auth.lower().startswith('bearer '):
        return auth[7:].strip() == token
    return request.headers.get('x-mmc-token', '').strip() == token


def _json_error(message: str, *, status: int = 400) -> JSONResponse:
    return JSONResponse({'ok': False, 'error': message}, status_code=status)


def _normalize_device_id(device_id: str) -> Optional[str]:
    did = str(device_id or '').strip().upper()
    if not _DEVICE_ID_RE.match(did):
        return None
    return did


def _config_exists(device_id: str) -> bool:
    return (_ALAS_ROOT / 'config' / f'{device_id}.json').is_file()


async def _health(_request: Request):
    return JSONResponse({
        'ok': True,
        'service': 'mmc-instance-api',
        'token_configured': bool(_load_expected_token()),
    })


async def _status(request: Request):
    if not _auth_ok(request):
        return _json_error('unauthorized', status=401)
    device_id = _normalize_device_id(request.path_params.get('device_id', ''))
    if not device_id:
        return _json_error('invalid device_id')
    pm = ProcessManager.get_manager(device_id)
    return JSONResponse({
        'ok': True,
        'device': device_id,
        'running': pm.alive,
        'state': pm.state,
    })


async def _start(request: Request):
    if not _auth_ok(request):
        return _json_error('unauthorized', status=401)
    device_id = _normalize_device_id(request.path_params.get('device_id', ''))
    if not device_id:
        return _json_error('invalid device_id')
    if not _config_exists(device_id):
        return _json_error(f'config not found: {device_id}.json', status=404)

    pm = ProcessManager.get_manager(device_id)
    if pm.alive:
        return JSONResponse({
            'ok': True,
            'device': device_id,
            'running': True,
            'message': f'{device_id} 已在运行',
        })

    try:
        func = get_config_mod(device_id)
        pm.start(func, updater.event)
    except Exception as e:
        logger.exception('instance_api start %s: %s', device_id, e)
        return _json_error(f'start failed: {e}', status=500)

    deadline = time.monotonic() + 8.0
    while not pm.alive and time.monotonic() < deadline:
        time.sleep(0.2)

    if not pm.alive:
        return _json_error(
            f'{device_id} ProcessManager 启动后未存活，请查看 log/{device_id}.txt',
            status=500,
        )

    logger.info('instance_api started %s via ProcessManager', device_id)
    return JSONResponse({
        'ok': True,
        'device': device_id,
        'running': True,
        'message': f'{device_id} 已通过 WebUI ProcessManager 启动',
    })


async def _stop(request: Request):
    if not _auth_ok(request):
        return _json_error('unauthorized', status=401)
    device_id = _normalize_device_id(request.path_params.get('device_id', ''))
    if not device_id:
        return _json_error('invalid device_id')

    pm = ProcessManager.get_manager(device_id)
    if not pm.alive:
        return JSONResponse({
            'ok': True,
            'device': device_id,
            'running': False,
            'message': f'{device_id} 未在运行',
        })

    try:
        pm.stop()
    except Exception as e:
        logger.exception('instance_api stop %s: %s', device_id, e)
        return _json_error(f'stop failed: {e}', status=500)

    return JSONResponse({
        'ok': True,
        'device': device_id,
        'running': pm.alive,
        'message': f'{device_id} 已停止',
    })


def build_instance_routes() -> list[Route]:
    return [
        Route('/mmc/instance/health', _health, methods=['GET']),
        Route('/mmc/instance/{device_id}/status', _status, methods=['GET']),
        Route('/mmc/instance/{device_id}/start', _start, methods=['POST']),
        Route('/mmc/instance/{device_id}/stop', _stop, methods=['POST']),
    ]
