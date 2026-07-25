"""
Alas 子路径 ASGI 代理：HTTP + WebSocket（PyWebIO 需要 WS）。
并支持根路径的 /pywebio_static、/static 指向上游（HTML 里多为绝对路径，否则会打到 Flask 404）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable, Tuple
from urllib.parse import urlparse

import httpx
from starlette._utils import get_route_path
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from proalas.device_cookie import get_device_id_from_cookie_header
from proalas.models_devices import list_config_device_ids


def _cfg():
    from proalas.config import Config

    return Config()


def _build_locked_ui_inject(allowed_config: str, cfg_dir: str) -> str:
    all_configs = sorted(set(list_config_device_ids(cfg_dir)))
    allowed_json = json.dumps(allowed_config, ensure_ascii=False)
    config_list_json = json.dumps(all_configs, ensure_ascii=False)
    return f"""
<style>#alas-gateway-banner{{position:fixed;right:16px;bottom:16px;z-index:100000;
background:rgba(22,163,74,.95);color:#fff;padding:8px 12px;border-radius:8px;font-size:12px;}}</style>
<script>
(function(){{const allowedConfig={allowed_json};const allConfigs={config_list_json};
function hideWrong(){{document.querySelectorAll('a,button,li,[role=button],div,span').forEach(function(el){{
const t=(el.textContent||'').trim();if(!t||t.length>32||!allConfigs.includes(t))return;
const c=el.closest('a,button,li,[role=button]')||el;if((c.textContent||'').trim()!==t)return;
c.style.display=(t===allowedConfig)?'':'none';}});}}
function openIfNeeded(){{for(const el of document.querySelectorAll('a,button,li,[role=button],div,span')){{
const t=(el.textContent||'').trim();if(t!==allowedConfig)continue;const c=el.closest('a,button,li,[role=button]')||el;
if(c.style.display!=='none'){{c.click();break;}}}}}}
window.addEventListener('message',function(ev){{if(ev&&ev.data&&ev.data.type==='dap:focus-config'){{hideWrong();openIfNeeded();}}}});
function boot(){{hideWrong();openIfNeeded();}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
setInterval(function(){{hideWrong();openIfNeeded();}},800);
if(!document.getElementById('alas-gateway-banner')){{const d=document.createElement('div');
d.id='alas-gateway-banner';d.textContent='已锁定配置: '+allowedConfig;document.body.appendChild(d);}}
}})();
</script>
"""


def _override_json_body(raw: bytes, allowed: str) -> Tuple[bytes, bool]:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return raw, False
    if not isinstance(obj, dict):
        return raw, False
    changed = False
    for k in ("config", "config_name", "configName", "filename", "profile"):
        if k in obj and obj[k] != allowed:
            obj[k] = allowed
            changed = True
    if not changed:
        return raw, False
    return json.dumps(obj, ensure_ascii=False).encode("utf-8"), True


def _query_override_multi(qp, allowed: str) -> str:
    from urllib.parse import urlencode

    d = dict(qp)
    for k in ("config", "config_name", "configName", "filename", "profile"):
        if k in d:
            d[k] = allowed
    return urlencode(d, doseq=True)


def _strip_proxy_headers(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    skip = {
        "content-length",
        "transfer-encoding",
        "x-frame-options",
        "content-security-policy",
        "content-encoding",
    }
    return [(k, v) for k, v in items if k.lower() not in skip]


def _rewrite_location_any(loc: str, upstream_base: str, public_origin: str) -> str:
    """把上游 Location 换成当前站点同源 URL（保留 /alas、/pywebio_static、/static 等路径）。"""
    up = upstream_base.rstrip("/")
    if loc.startswith(up):
        return public_origin.rstrip("/") + loc[len(up) :]
    p = urlparse(loc)
    up_p = urlparse(upstream_base)
    if p.netloc == up_p.netloc and p.scheme == up_p.scheme:
        return public_origin.rstrip("/") + (p.path or "/") + (f"?{p.query}" if p.query else "")
    return loc


def _upstream_url_for_alas(request: Request, allowed: str) -> tuple[str, bool]:
    """返回 (完整上游 URL, 是否做 JSON 里 config 覆盖)。"""
    cfg = _cfg()
    upstream = cfg.ALAS_UPSTREAM.rstrip("/")
    # Mount 下 request.url.path 仍是完整 ASGI path（含 /alas），必须用 root_path 后的路由路径
    sub = get_route_path(request.scope).lstrip("/")
    url = f"{upstream}/{sub}" if sub else f"{upstream}/"
    if request.url.query:
        url = f"{url}?{_query_override_multi(request.query_params, allowed)}"
    return url, True


def _upstream_url_for_prefix(request: Request, allowed: str, segment: str) -> tuple[str, bool]:
    cfg = _cfg()
    upstream = cfg.ALAS_UPSTREAM.rstrip("/")
    sub = get_route_path(request.scope).lstrip("/")
    rel = f"{segment}/{sub}" if sub else f"{segment}/"
    url = f"{upstream}/{rel}"
    if request.url.query:
        url = f"{url}?{_query_override_multi(request.query_params, allowed)}"
    return url, False


async def _do_proxy_http(
    request: Request,
    url: str,
    *,
    override_json: bool,
    inject_html: bool,
    allowed: str,
) -> Response:
    cfg = _cfg()
    hdrs = []
    for k, v in request.headers.items():
        if k.lower() in ("host", "connection", "content-length"):
            continue
        hdrs.append((k, v))

    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()
        ct = request.headers.get("content-type", "")
        if override_json and "application/json" in ct and body:
            body, _ = _override_json_body(body, allowed)

    public_origin = f"{request.url.scheme}://{request.url.netloc}"
    upstream_base = cfg.ALAS_UPSTREAM.rstrip("/")

    # trust_env=False：避免系统 HTTP_PROXY 把 127.0.0.1 拐走（浏览器能开、DAP 502）
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        try:
            r = await client.request(request.method, url, headers=dict(hdrs), content=body)
        except httpx.ConnectError as e:
            return Response(
                f"<html><body>无法连接 Alas: {upstream_base}<br/>原因: {e}</body></html>",
                status_code=502,
                media_type="text/html",
            )
        except httpx.HTTPError as e:
            return Response(
                f"<html><body>Alas 代理错误: {upstream_base}<br/>原因: {e}</body></html>",
                status_code=502,
                media_type="text/html",
            )

    if 300 <= r.status_code < 400 and r.headers.get("location"):
        new_loc = _rewrite_location_any(r.headers["location"], upstream_base, public_origin)
        return Response(status_code=r.status_code, headers={"location": new_loc})

    ct = r.headers.get("content-type", "")
    out_items = _strip_proxy_headers(list(r.headers.items()))

    if inject_html and ct.startswith("text/html"):
        html = r.text
        inj = _build_locked_ui_inject(allowed, cfg.CONFIG_DIR)
        if "</body>" in html:
            html = html.replace("</body>", inj + "</body>")
        else:
            html += inj
        return Response(
            html,
            status_code=r.status_code,
            headers=dict(out_items),
            media_type=ct.split(";")[0].strip(),
        )

    return Response(
        content=r.content,
        status_code=r.status_code,
        headers=dict(out_items),
        media_type=ct.split(";")[0].strip() if ct else None,
    )


def _resolve_allowed_device(request) -> tuple[str | None, Response | None]:
    cfg = _cfg()
    allowed = get_device_id_from_cookie_header(request.headers.get("cookie"), cfg.SECRET_KEY)
    if not allowed:
        return None, Response("Unauthorized", status_code=401)
    from proalas.account_expiry import device_is_expired

    if device_is_expired(cfg.CONFIG_DIR, allowed):
        return None, Response("服务已过期", status_code=403)
    return allowed, None


async def alas_http(request: Request) -> Response:
    allowed, denied = _resolve_allowed_device(request)
    if denied is not None:
        return denied
    url, override_json = _upstream_url_for_alas(request, allowed)
    return await _do_proxy_http(request, url, override_json=override_json, inject_html=True, allowed=allowed)


def _make_prefix_http(segment: str) -> Callable:
    async def prefix_http(request: Request) -> Response:
        allowed, denied = _resolve_allowed_device(request)
        if denied is not None:
            return denied
        url, override_json = _upstream_url_for_prefix(request, allowed, segment)
        return await _do_proxy_http(request, url, override_json=override_json, inject_html=False, allowed=allowed)

    return prefix_http


async def alas_websocket(websocket: WebSocket):
    await websocket.accept()
    allowed, denied = _resolve_allowed_device(websocket)
    if denied is not None:
        await websocket.close(code=4403)
        return

    cfg = _cfg()
    upstream_http = cfg.ALAS_UPSTREAM.rstrip("/")
    upstream_ws = upstream_http.replace("http://", "ws://").replace("https://", "wss://")

    sub = get_route_path(websocket.scope).lstrip("/")
    ws_url = f"{upstream_ws}/{sub}" if sub else f"{upstream_ws}/"
    if websocket.query_params:
        ws_url += "?" + _query_override_multi(websocket.query_params, allowed)

    try:
        import websockets

        async with websockets.connect(ws_url, max_size=None) as up:

            async def c2u():
                try:
                    while True:
                        raw = await websocket.receive()
                        if raw["type"] == "websocket.disconnect":
                            return
                        if "text" in raw:
                            await up.send(raw["text"])
                        elif "bytes" in raw:
                            await up.send(raw["bytes"])
                except WebSocketDisconnect:
                    return
                except Exception:
                    return

            async def u2c():
                try:
                    while True:
                        msg = await up.recv()
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    return

            await asyncio.gather(c2u(), u2c(), return_exceptions=True)
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


async def _reject_ws(websocket: WebSocket):
    await websocket.close(code=4404)


def build_alas_app() -> Starlette:
    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
    return Starlette(
        routes=[
            WebSocketRoute("/", alas_websocket),
            WebSocketRoute("/{path:path}", alas_websocket),
            Route("/", alas_http, methods=methods),
            Route("/{path:path}", alas_http, methods=methods),
        ],
    )


def build_upstream_prefix_app(segment: str) -> Starlette:
    """代理上游固定前缀路径（如 pywebio_static、static），仅 HTTP。"""
    h = _make_prefix_http(segment)
    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
    return Starlette(
        routes=[
            WebSocketRoute("/", _reject_ws),
            WebSocketRoute("/{path:path}", _reject_ws),
            Route("/", h, methods=methods),
            Route("/{path:path}", h, methods=methods),
        ],
    )
