# -*- coding: utf-8 -*-
"""
临时远控反代：浏览器 → DAP → mmc-agent → 本机 ws-scrcpy。

ws-scrcpy-web 在 iframe 内会：
1) 请求绝对路径 /api/*（打到 DAP 根）
2) 在 /remote/http/{ticket}/ 上升级 WebSocket（multiplex）
3) 另开绝对路径 WebSocket（ws://dap/ 等），若落入 Flask WSGI 会 AssertionError

因此需要：/remote 下的 HTTP+WS、根路径 /api，以及兜底 WS 中间件。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketDisconnect

from proalas.device_cookie import get_device_id_from_cookie_header
from proalas.remote_control import active_ticket_for_device, lookup_ticket

logger = logging.getLogger(__name__)

REMOTE_TICKET_COOKIE = 'proalas_rt'


def _cfg():
    from proalas.config import Config
    return Config()


def _session_device_from_cookie(cookie: str) -> str:
    return (get_device_id_from_cookie_header(cookie) or '').upper().strip()


def _ticket_from_cookie(cookie: str) -> str:
    if not cookie:
        return ''
    for chunk in cookie.split(';'):
        chunk = chunk.strip()
        if chunk.lower().startswith(REMOTE_TICKET_COOKIE.lower() + '='):
            return chunk.split('=', 1)[1].strip()
    return ''


def _cookie_from_scope(scope: Scope) -> str:
    headers = {
        k.decode().lower(): v.decode()
        for k, v in (scope.get('headers') or [])
    }
    return headers.get('cookie') or ''


def _resolve_ticket_meta(ticket: str, session_device: str) -> tuple[Optional[dict], Optional[str]]:
    meta = lookup_ticket(ticket)
    if not meta:
        return None, 'ticket 无效或已过期'
    if not session_device:
        return None, '请先登录 DAP'
    if meta.get('device_id') != session_device:
        return None, 'ticket 与当前登录设备不符'
    return meta, None


def _resolve_ticket_for_scope(scope: Scope) -> tuple[str, Optional[str]]:
    """返回 (ticket, error)。"""
    cookie = _cookie_from_scope(scope)
    device = _session_device_from_cookie(cookie)
    ticket = _ticket_from_cookie(cookie)
    if ticket:
        meta, err = _resolve_ticket_meta(ticket, device)
        if not err:
            return ticket, None
    if device:
        t2 = active_ticket_for_device(device)
        if t2:
            return t2, None
    return '', '无活跃远控会话'


def _mmc_root() -> str:
    cfg = _cfg()
    url = (cfg.MMC_COMMAND_URL or '').strip().rstrip('/')
    for suffix in ('/mmc/command', '/mmc'):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip('/')


def _mmc_ws_base() -> str:
    root = _mmc_root()
    if root.startswith('https://'):
        return 'wss://' + root[len('https://'):]
    if root.startswith('http://'):
        return 'ws://' + root[len('http://'):]
    return root


def _ws_connect(uri: str, headers: dict[str, str], subprotocols: Optional[list] = None):
    import websockets

    kwargs = {'max_size': 8 * 1024 * 1024, 'open_timeout': 20}
    if subprotocols:
        kwargs['subprotocols'] = list(subprotocols)
    try:
        return websockets.connect(uri, additional_headers=headers, **kwargs)
    except TypeError:
        try:
            return websockets.connect(uri, extra_headers=headers, **kwargs)
        except TypeError:
            return websockets.connect(uri, **kwargs)


async def _bridge_websockets(client: WebSocket, upstream) -> None:
    async def client_to_upstream():
        try:
            while True:
                message = await client.receive()
                if message['type'] == 'websocket.receive':
                    if message.get('text') is not None:
                        await upstream.send(message['text'])
                    elif message.get('bytes') is not None:
                        await upstream.send(message['bytes'])
                elif message['type'] == 'websocket.disconnect':
                    break
        except WebSocketDisconnect:
            pass

    async def upstream_to_client():
        try:
            async for data in upstream:
                if isinstance(data, bytes):
                    await client.send_bytes(data)
                else:
                    await client.send_text(str(data))
        except Exception:
            pass

    _done, pending = await asyncio.wait(
        [
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()


async def _proxy_ws_to_mmc(websocket: WebSocket, ticket: str) -> None:
    session_device = _session_device_from_cookie(_cookie_from_scope(websocket.scope))
    meta, err = _resolve_ticket_meta(ticket, session_device)
    if err or not meta:
        logger.warning('remote ws reject ticket=%s: %s', ticket[:8] if ticket else '-', err)
        await websocket.close(code=4403)
        return

    root_ws = _mmc_ws_base()
    if not root_ws:
        await websocket.close(code=1011)
        return

    target = f'{root_ws}/mmc/remote/stream/{ticket}'
    qs = websocket.scope.get('query_string') or b''
    if qs:
        target = f'{target}?{qs.decode()}'

    cfg = _cfg()
    headers = {}
    token = (cfg.MMC_COMMAND_TOKEN or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'

    subprotocols = list(websocket.scope.get('subprotocols') or [])

    try:
        import websockets  # noqa: F401
    except ImportError:
        logger.error('DAP 缺少 websockets 包，无法反代远控 WS')
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
        return

    try:
        # 先连上游再 accept，避免浏览器看到「连上又秒断」却不知原因
        async with _ws_connect(target, headers, subprotocols or None) as upstream_ws:
            sp = subprotocols[0] if subprotocols else None
            try:
                await websocket.accept(subprotocol=sp)
            except TypeError:
                await websocket.accept()
            logger.info('remote ws bridged ticket=%s target=%s', ticket[:8], target)
            await _bridge_websockets(websocket, upstream_ws)
    except Exception as e:
        logger.warning('remote ws proxy failed ticket=%s target=%s: %s', ticket[:8], target, e)
        try:
            await websocket.accept()
            await websocket.close(code=1011)
        except Exception:
            pass


async def remote_ws(websocket: WebSocket):
    ticket = str(websocket.path_params.get('ticket') or '').strip()
    await _proxy_ws_to_mmc(websocket, ticket)


async def remote_http_ws(websocket: WebSocket):
    ticket = str(websocket.path_params.get('ticket') or '').strip()
    await _proxy_ws_to_mmc(websocket, ticket)


async def _forward_http_to_mmc(request: Request, ticket: str, rest: str) -> Response:
    session_device = _session_device_from_cookie(request.headers.get('cookie') or '')
    meta, err = _resolve_ticket_meta(ticket, session_device)
    if err or not meta:
        return Response(err or 'forbidden', status_code=403)

    root = _mmc_root()
    if not root:
        return Response('MMC_COMMAND_URL missing', status_code=502)

    rest = (rest or '').lstrip('/')
    url = f'{root}/mmc/remote/http/{ticket}/{rest}' if rest else f'{root}/mmc/remote/http/{ticket}'
    qs = request.scope.get('query_string') or b''
    if qs:
        url = f'{url}?{qs.decode()}'

    cfg = _cfg()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ('host', 'content-length')
    }
    token = (cfg.MMC_COMMAND_TOKEN or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            upstream = await client.request(
                request.method,
                url,
                content=await request.body(),
                headers=headers,
            )
        excluded = {'content-encoding', 'transfer-encoding', 'content-length'}
        out_headers = {
            k: v for k, v in upstream.headers.items()
            if k.lower() not in excluded
        }
        return Response(upstream.content, status_code=upstream.status_code, headers=out_headers)
    except Exception as e:
        logger.warning('remote http proxy failed: %s', e)
        return Response(f'proxy error: {e}', status_code=502)


async def remote_http_proxy(request: Request) -> Response:
    ticket = str(request.path_params.get('ticket') or '').strip()
    rest = str(request.path_params.get('rest') or '').lstrip('/')
    return await _forward_http_to_mmc(request, ticket, rest)


async def remote_root_api_proxy(request: Request) -> Response:
    cookie = request.headers.get('cookie') or ''
    device = _session_device_from_cookie(cookie)
    ticket = _ticket_from_cookie(cookie) or (
        active_ticket_for_device(device) if device else None
    )
    if not ticket:
        return Response('no active remote session', status_code=404)
    rest = str(request.path_params.get('rest') or '').lstrip('/')
    path = f'api/{rest}' if rest else 'api'
    return await _forward_http_to_mmc(request, ticket, path)


async def _ws_http_reject(scope: Scope, receive: Receive, send: Send, status: int = 403) -> None:
    await send({
        'type': 'websocket.http.response.start',
        'status': status,
        'headers': [(b'content-type', b'text/plain')],
    })
    await send({
        'type': 'websocket.http.response.body',
        'body': b'websocket rejected',
        'more_body': False,
    })


class ActiveRemoteWebSocketMiddleware:
    """
    拦截会落到 Flask WSGI 的 WebSocket（绝对路径 ws://dap/），
    有活跃远控则反代，否则干净拒绝，避免 AssertionError。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'websocket':
            await self.app(scope, receive, send)
            return

        path = scope.get('path') or ''
        if path.startswith('/alas') or path.startswith('/remote'):
            await self.app(scope, receive, send)
            return

        ticket, err = _resolve_ticket_for_scope(scope)
        if not ticket:
            logger.info('root ws reject path=%s err=%s', path, err)
            await _ws_http_reject(scope, receive, send, 403)
            return

        websocket = WebSocket(scope, receive=receive, send=send)
        await _proxy_ws_to_mmc(websocket, ticket)


def build_remote_app() -> Starlette:
    return Starlette(
        routes=[
            WebSocketRoute('/ws/{ticket}', remote_ws),
            WebSocketRoute('/http/{ticket}', remote_http_ws),
            WebSocketRoute('/http/{ticket}/', remote_http_ws),
            WebSocketRoute('/http/{ticket}/{rest:path}', remote_http_ws),
            Route('/http/{ticket}', remote_http_proxy, methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']),
            Route('/http/{ticket}/', remote_http_proxy, methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']),
            Route('/http/{ticket}/{rest:path}', remote_http_proxy, methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']),
        ],
    )


def build_api_proxy_routes() -> list:
    methods = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
    return [
        Route('/api', remote_root_api_proxy, methods=methods),
        Route('/api/{rest:path}', remote_root_api_proxy, methods=methods),
    ]
